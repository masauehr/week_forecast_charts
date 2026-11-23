#!/usr/bin/env python
# coding: utf-8
"""公開サイト（gh-pages）で GitHub Actions が作った図を、手元の output/ へ取り込む。

目的: Actions が作った新しい初期値は公開側にしか無く、ローカル版（serve_local.py）に出ない。
      GRIB2 は公開側にも無い（PNG・manifest・画面だけ）ので、手元で作り直すと ENS は2時間強かかる。
      公開済みの PNG を取り込めば、数十秒〜数分で手元でも同じ図が見られる。
取り込むもの:
  統計図   charts/{初期値}/        → output/{初期値}/
  天気図   maps/output/{ens,gefs}/{初期値}/ → output/maps/{ens,gefs}/{初期値}/
  ※ GSM（ローカル専用）には触れない。公開側に無い初期値だけを足し、既にある初期値は取り直さない。
動作: 公開ブランチの先頭コミットが前回と同じなら何もしない（--force で取り込む）。
整理: 手元の統計図・ens・gefs のうち、公開側の最も古い初期値より古いものを消す（--keep-local で残す）。GSM は消さない。

使用例:
  python sync_public.py            # 変更があれば取り込む（launchd・画面の「同期」ボタンから呼ぶ）
  python sync_public.py --force
  python sync_public.py --prune-only --dry-run
"""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
STATE = ROOT / "logs" / "sync_state.json"
INIT_RE = re.compile(r"\d{10}")
PUBLIC_MODELS = ("ens", "gefs")          # 公開されるモデル（GSM はローカル専用なので対象外）


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def git(*args, check=True, binary=False):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} に失敗: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r if binary else r.stdout.decode("utf-8", "replace")


def fetch_tip(remote, branch):
    """公開ブランチの先頭コミットを取得する（取れなければ None）。"""
    r = subprocess.run(["git", "fetch", "--depth", "1", remote, branch], cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        return None
    return git("rev-parse", "FETCH_HEAD").strip()


def ls_dirs(tip, path):
    """tip の path 直下のサブディレクトリ名（無ければ空）。"""
    r = subprocess.run(["git", "ls-tree", "-d", "--name-only", f"{tip}:{path}"], cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        return []
    return [n for n in r.stdout.decode("utf-8").split() if n]


def extract(tip, path, dst):
    """tip の path（ディレクトリ）を dst へ展開する。"""
    r = git("archive", "--format=tar", tip, path, binary=True)
    tmp = dst.parent / (dst.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
            tf.extractall(tmp, filter="data")
        shutil.rmtree(dst, ignore_errors=True)
        shutil.move(str(tmp / path), str(dst))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def local_inits(d):
    return sorted([p.name for p in d.iterdir() if p.is_dir() and INIT_RE.fullmatch(p.name)]) if d.is_dir() else []


def prune(public, dry_run=False):
    """公開側の最も古い初期値より古い手元の初期値を消す。public = {対象名: 公開側の初期値のリスト}。"""
    n = 0
    targets = {"stat": OUT, **{m: OUT / "maps" / m for m in PUBLIC_MODELS}}
    for key, d in targets.items():
        pub = public.get(key) or []
        if not pub:                       # 公開側が取れていないときは消さない
            continue
        oldest = min(pub)
        for i in local_inits(d):
            if i < oldest:
                n += 1
                log(f"古い初期値を削除{' [dry-run]' if dry_run else ''}: {key}/{i}")
                if not dry_run:
                    shutil.rmtree(d / i)
    return n


def write_manifests():
    """統計図・天気図の manifest を手元の画像から作り直す。"""
    sys.path.insert(0, str(ROOT))
    import publish
    man = publish.build_manifest(OUT, keep=publish.KEEP_DEFAULT)
    (OUT / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    if (OUT / "maps").is_dir():
        import maps_manifest
        maps_manifest.write_manifest(OUT / "maps")


def sync(tip):
    public = {}
    got = 0
    # 統計図
    pub = sorted([i for i in ls_dirs(tip, "charts") if INIT_RE.fullmatch(i)])
    public["stat"] = pub
    for i in pub:
        if (OUT / i).is_dir() and any((OUT / i).glob("*.png")):
            continue
        log(f"統計図を取り込み: {i}")
        extract(tip, f"charts/{i}", OUT / i)
        got += 1
    # 天気図
    for m in PUBLIC_MODELS:
        pub = sorted([i for i in ls_dirs(tip, f"maps/output/{m}") if INIT_RE.fullmatch(i)])
        public[m] = pub
        for i in pub:
            dst = OUT / "maps" / m / i
            if dst.is_dir() and any(dst.rglob("*.png")):
                continue
            log(f"天気図を取り込み: {m}/{i}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            extract(tip, f"maps/output/{m}/{i}", dst)
            got += 1
    return public, got


def main():
    ap = argparse.ArgumentParser(description="公開済みの図を手元へ取り込む")
    ap.add_argument("--force", action="store_true", help="変更の有無にかかわらず確認する")
    ap.add_argument("--no-prune", action="store_true", help="古い初期値を消さない")
    ap.add_argument("--prune-only", action="store_true", help="取り込まず整理だけ行う（--dry-run で対象表示のみ）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="gh-pages")
    a = ap.parse_args()
    tip = None
    for k in range(4):                      # スリープ復帰直後はネットワーク未接続のことがあるので20秒おきに最大4回
        tip = fetch_tip(a.remote, a.branch)
        if tip is not None:
            break
        if k < 3:
            time.sleep(20)
    if tip is None:
        log("公開ブランチを取得できません（ネットワークを確認）")
        return 1
    last = json.loads(STATE.read_text(encoding="utf-8")).get("tip") if STATE.exists() else None
    if tip == last and not a.force and not a.prune_only:
        log("公開側に変更はありません")
        return 0
    OUT.mkdir(exist_ok=True)
    if a.prune_only:
        public = {"stat": sorted(i for i in ls_dirs(tip, "charts") if INIT_RE.fullmatch(i))}
        for m in PUBLIC_MODELS:
            public[m] = sorted(i for i in ls_dirs(tip, f"maps/output/{m}") if INIT_RE.fullmatch(i))
        prune(public, a.dry_run)
        if not a.dry_run:
            write_manifests()
        return 0
    public, got = sync(tip)
    if not a.no_prune:
        prune(public)
    write_manifests()
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"tip": tip, "synced": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    log(f"取り込み完了（新規 {got} 件・manifest を更新しました）" if got else "取り込み完了（新しい初期値はありません）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
