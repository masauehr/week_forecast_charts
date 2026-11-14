#!/usr/bin/env python
# coding: utf-8
"""作成したPNGを公開ブランチ(gh-pages)へ反映する。GRIB2 は載せない（PNG・manifest・画面だけ）。

方式（nwp_chart_web の publish.py と同じ考え方）:
  1. 公開ブランチを取り込み、新しい初期値のPNGを charts/{初期値}/ に足す
  2. 古い初期値を keep 個を超えた分だけ削除
  3. manifest.json を作り直し、web/ があれば画面ファイルも載せる
  4. 履歴を溜めない単一の孤立コミットとして force push（容量を増やさない）

例: python publish.py --src output/2026111312
    python publish.py --web-only                  （画面だけ差し替え。図は公開ブランチのまま）
    python publish.py --src output/2026111312 --remote /tmp/bare.git   （ローカル検証）
CI では環境変数 GITHUB_REPOSITORY / GITHUB_TOKEN から公開先を決める。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BRANCH = "gh-pages"
MAPS_KEEP = 3                        # 天気図（アンサンブル平均）で残す初期値の数（モデルごと。1初期値約60MB×2モデル）
ROOT = Path(__file__).resolve().parent
KEEP_DEFAULT = 8                     # 残す初期値の数（1日2回×4日分。1初期値約7MB）
# ファイル名: ecmwf-ens_2026111312_c1_p1_asia.png / ..._c2_f168_asia.png / ..._c3high_p2_nh.png
NAME_RE = re.compile(r"^(?P<model>[a-z0-9-]+)_(?P<init>\d{10})_(?P<chart>c[123](?:high|low)?)_"
                     r"(?P<sel>[pf]\d+)_(?P<region>[a-z]+)\.png$")

LEGAL = {
    "source": "ECMWF Open Data (IFS ENS), licensed under CC BY 4.0. © ECMWF. "
              "Modified: the data were statistically processed into charts. ECMWF does not accept any liability "
              "for any error or omission in the data.",
    "climatology": "NCEP/NCAR Reanalysis daily long-term mean 1991-2020 (NOAA PSL)",
    "disclaimer": "アンサンブル統計に基づく傾向であり、気象庁の公式予報ではありません。"
                  "防災に関わる判断には気象庁の情報を使ってください。",
}


def parse_name(name: str):
    """PNGのファイル名 → 属性の辞書。想定外の名前は None。"""
    m = NAME_RE.match(name)
    if not m:
        return None
    d = m.groupdict()
    sel = d["sel"]
    return dict(name=name, model=d["model"], init=d["init"], chart=d["chart"],
                kind="period" if sel[0] == "p" else "step", value=int(sel[1:]), region=d["region"])


def build_manifest(charts_dir: Path, keep: int = KEEP_DEFAULT, now=None):
    """charts_dir/{初期値}/*.png を走査して manifest を作る。新しい初期値から keep 個まで。"""
    inits = sorted([p.name for p in Path(charts_dir).iterdir() if p.is_dir() and re.fullmatch(r"\d{10}", p.name)],
                   reverse=True)[:keep]
    out = []
    for i in inits:
        files = [a for a in (parse_name(f.name) for f in sorted((Path(charts_dir) / i).glob("*.png"))) if a]
        out.append(dict(init=i, files=files))
    now = now or datetime.now(timezone.utc)
    return dict(updated=now.strftime("%Y-%m-%dT%H:%MZ"), inits=out, legal=LEGAL)


def prune(charts_dir: Path, keep: int = KEEP_DEFAULT):
    """keep を超えた古い初期値のフォルダを削除し、削除した名前を返す。"""
    inits = sorted([p for p in Path(charts_dir).iterdir() if p.is_dir() and re.fullmatch(r"\d{10}", p.name)],
                   key=lambda p: p.name, reverse=True)
    gone = []
    for p in inits[keep:]:
        shutil.rmtree(p)
        gone.append(p.name)
    return gone


def published_inits(repo: str | None = None, timeout=30):
    """公開サイト(Pages)の manifest.json から、公開済みの初期値(YYYYMMDDHH)の集合を返す。取れなければ空集合。

    cron-job.org の起動で「すでに公開済みなら何もしない」ための判定に使う。Pages のキャッシュで最大数分遅れるが、
    二重に作っても結果は同じ（冪等）。
    """
    import requests
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        return set()
    owner, name = repo.split("/", 1)
    url = f"https://{owner}.github.io/{name}/manifest.json?t={int(datetime.now().timestamp())}"
    try:
        r = requests.get(url, timeout=timeout, headers={"Cache-Control": "no-cache"})
        r.raise_for_status()
        return {i["init"] for i in r.json().get("inits", [])}
    except Exception as e:                       # 取れなければ作る側に倒す（安全側）
        print("公開済みの確認に失敗（作る側に倒す）:", e)
        return set()


def published_map_inits(model: str, repo: str | None = None, timeout=30):
    """公開サイトの maps/output/manifest.json から、そのモデルの公開済みの初期値の集合を返す。取れなければ空集合。"""
    import requests
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        return set()
    owner, name = repo.split("/", 1)
    url = f"https://{owner}.github.io/{name}/maps/output/manifest.json?t={int(datetime.now().timestamp())}"
    try:
        r = requests.get(url, timeout=timeout, headers={"Cache-Control": "no-cache"})
        r.raise_for_status()
        return {i["init"] for i in r.json().get("models", {}).get(model, {}).get("inits", [])}
    except Exception as e:
        print("公開済みの確認に失敗（作る側に倒す）:", e)
        return set()


def _git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def remote_url(remote=None):
    if remote:
        return remote
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if repo and token:
        return f"https://x-access-token:{token}@github.com/{repo}.git"
    raise SystemExit("公開先が不明です。--remote を指定するか GITHUB_REPOSITORY と GITHUB_TOKEN を設定してください")


def _maps_list(maps_src):
    """maps_src（None・1つのPath・Pathのリスト）をリストにそろえる。"""
    if maps_src is None:
        return []
    return [Path(p) for p in (maps_src if isinstance(maps_src, (list, tuple)) else [maps_src])]


def _publish_maps(pub: Path, maps_src, maps_keep: int, maps_web: Path | None):
    """天気図（アンサンブル平均）: maps/ に画面と output/{model}/{init}/ を載せ、manifest を作り直す。"""
    mroot = pub / "maps"
    out = mroot / "output"
    gone = []
    srcs = _maps_list(maps_src)
    import maps_manifest
    for src in srcs:
        model, init = src.parent.name, src.name                      # output/maps/{model}/{init}
        if model in maps_manifest.LOCAL_ONLY:
            raise SystemExit(f"{model} はローカル専用のモデルなので公開できません: {src}")
        if not re.fullmatch(r"\d{10}", init):
            raise SystemExit(f"--maps-src は {{model}}/{{初期値YYYYMMDDHH}} のフォルダにしてください: {src}")
        dst = out / model / init
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        inits = sorted([p for p in (out / model).iterdir() if p.is_dir() and re.fullmatch(r"\d{10}", p.name)],
                       key=lambda p: p.name, reverse=True)
        for p in inits[maps_keep:]:
            shutil.rmtree(p)
            gone.append(f"{model}/{p.name}")
    if maps_web and Path(maps_web).exists():                         # 画面（標準版・画用紙版）
        shutil.copytree(maps_web, mroot, dirs_exist_ok=True)
    if srcs:                                                         # 図が増減したときだけ manifest を作り直す
        maps_manifest.write_manifest(out, public_only=True)             # 公開用はローカル専用モデルを載せない
    return gone


def publish(src: Path | None, remote=None, keep=KEEP_DEFAULT, web_dir: Path | None = None, dry_run=False,
            maps_src: Path | None = None, maps_keep=MAPS_KEEP, maps_web: Path | None = None):
    """src=None かつ maps_src=None なら画面だけを差し替える（図は公開ブランチのものをそのまま残す）。
    src: 統計図(charts/) の初期値フォルダ。maps_src: 天気図(maps/output/{model}/{init}) のフォルダ。"""
    pngs, init = [], None
    if src is not None:
        src = Path(src)
        init = src.name
        if not re.fullmatch(r"\d{10}", init):
            raise SystemExit(f"--src は初期値(YYYYMMDDHH)名のフォルダにしてください: {src}")
        pngs = sorted(src.glob("*.png"))
        if not pngs:
            raise SystemExit(f"{src} にPNGがありません")
    url = remote_url(remote) if not dry_run else None

    with tempfile.TemporaryDirectory(prefix="wsc_pub_") as td:
        pub = Path(td) / "pub"
        pub.mkdir()
        if url:
            r = subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, url, str(pub / "_old")],
                               capture_output=True, text=True)
            if r.returncode == 0:                      # 既存の公開内容(charts/・maps/output/)を引き継ぐ
                for rel in ("charts", "maps/output"):
                    old = pub / "_old" / rel
                    if old.exists():
                        shutil.copytree(old, pub / rel)
                shutil.rmtree(pub / "_old", ignore_errors=True)
        charts = pub / "charts"
        if init:
            (charts / init).mkdir(parents=True, exist_ok=True)
            for f in pngs:
                shutil.copy2(f, charts / init / f.name)
        elif not charts.exists() and not _maps_list(maps_src) and not (pub / "maps").exists():
            raise SystemExit("--web-only には公開済みの図が必要です（先に図を公開してください）")
        if charts.exists():
            gone = prune(charts, keep)
            man = build_manifest(charts, keep)
            (pub / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            gone, man = [], {"inits": []}
        gone += _publish_maps(pub, maps_src, maps_keep, maps_web)
        (pub / ".nojekyll").write_text("", encoding="utf-8")
        if web_dir and Path(web_dir).exists():
            for f in Path(web_dir).iterdir():
                if f.is_file():
                    shutil.copy2(f, pub / f.name)
        print(f"公開内容: 初期値{[i['init'] for i in man['inits']]} 削除{gone} PNG{len(pngs)}枚")
        if dry_run:
            dst = Path(tempfile.gettempdir()) / "wsc_pub_dryrun"
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(pub, dst)
            print("dry-run: 反映先", dst)
            return man
        _git(pub, "init", "-q", "-b", BRANCH)
        _git(pub, "config", "user.name", "github-actions[bot]")
        _git(pub, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        _git(pub, "add", "-A")
        label = f"公開: {init}" if init else ("天気図: " + ", ".join(f"{p.parent.name}/{p.name}" for p in _maps_list(maps_src)) if maps_src else "画面の更新")
        _git(pub, "commit", "-q", "-m", label)
        _git(pub, "push", "-q", "--force", url, f"HEAD:{BRANCH}")
        print("反映しました")
        return man


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="統計図: output/<初期値YYYYMMDDHH> フォルダ")
    ap.add_argument("--maps-src", action="append", help="天気図: output/maps/<model>/<初期値YYYYMMDDHH> フォルダ（複数指定可）")
    ap.add_argument("--maps-keep", type=int, default=MAPS_KEEP, help="天気図で残す初期値の数（モデルごと）")
    ap.add_argument("--maps-web", default=str(ROOT / "maps_web"), help="天気図の画面（maps_web/）")
    ap.add_argument("--web-only", action="store_true", help="画面(web/)だけ差し替える。図は触らない")
    ap.add_argument("--remote", help="公開先URL/パス（省略時は GITHUB_REPOSITORY・GITHUB_TOKEN）")
    ap.add_argument("--keep", type=int, default=KEEP_DEFAULT)
    ap.add_argument("--web", default=str(Path(__file__).resolve().parent / "web"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.web_only and not a.src and not a.maps_src:
        ap.error("--src・--maps-src・--web-only のいずれかが必要です")
    publish(None if (a.web_only or not a.src) else Path(a.src), a.remote, a.keep, Path(a.web), a.dry_run,
            [Path(p) for p in a.maps_src] if (a.maps_src and not a.web_only) else None, a.maps_keep, Path(a.maps_web))
