#!/usr/bin/env python
# coding: utf-8
"""ローカル専用の GSM（気象庁・決定論）の天気図を、最新の揃った初期値まで自動で更新する（launchd から1時間おきに呼ぶ）。

動作: RISH で 0〜168h が全部揃った最新の初期値（00/12UTC）を調べ、手元に無ければ mean_pipeline.py --model gsm で作る。
      すでにあれば何もせず終わる（冪等・数秒）。作った後、初期時刻が --keep-days（既定3日）より古い GSM を削除する。
      GSM は公開しない（Actions では動かさない・publish しない）。ログ: logs/gsm.log
使用例:
  python update_gsm.py                  # 最新の初期値が無ければ作る
  python update_gsm.py --prune-only --dry-run
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GSM_DIR = ROOT / "output" / "maps" / "gsm"


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def made(init_text):
    """その初期値の PNG が手元にあるか。"""
    d = GSM_DIR / init_text
    return d.is_dir() and any(d.rglob("*.png"))


def prune(keep_days, dry_run=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    n = 0
    if not GSM_DIR.is_dir():
        return 0
    for sub in sorted(GSM_DIR.iterdir()):
        if not (sub.is_dir() and re.fullmatch(r"\d{10}", sub.name)):
            continue
        if (sub / ".keep").exists():          # 目印があれば残す
            continue
        if datetime.strptime(sub.name, "%Y%m%d%H").replace(tzinfo=timezone.utc) < cutoff:
            n += 1
            log(f"古い GSM を削除{' [dry-run]' if dry_run else ''}: {sub.name}")
            if not dry_run:
                shutil.rmtree(sub)
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep-days", type=float, default=3, help="手元に残す日数（初期時刻基準。0で整理しない）")
    ap.add_argument("--prune-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        raise SystemExit("GSM はローカル専用です（Actions では動かしません）")
    sys.path.insert(0, str(ROOT))
    import maps_manifest
    if a.prune_only:
        prune(a.keep_days, a.dry_run)
        if not a.dry_run:
            maps_manifest.write_manifest(ROOT / "output" / "maps")
        return 0
    import fetch_gsm
    init = fetch_gsm.find_latest_complete()
    if init is None:
        log("RISH に揃った初期値がありません（配信待ち・ネットワークを確認）")
        return 0
    text = f"{init:%Y%m%d%H}"
    if made(text):
        log(f"GSM {text} は作成済みです")
    else:
        log(f"GSM {text} を作成します（約8分）")
        r = subprocess.run([sys.executable, "-u", str(ROOT / "mean_pipeline.py"), "--model", "gsm", "--init", text], cwd=ROOT)
        if r.returncode != 0:
            log(f"作成に失敗しました（rc={r.returncode}）。次回の起動でやり直します")
            return r.returncode
        log(f"GSM {text} を作成しました")
    if a.keep_days > 0:
        prune(a.keep_days)
    maps_manifest.write_manifest(ROOT / "output" / "maps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
