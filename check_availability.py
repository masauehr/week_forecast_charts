#!/usr/bin/env python
# coding: utf-8
"""ECMWF ENS の初期値（00/12UTC）が「いつ揃うか」を実測して記録する。

目的: cron-job.org の起動時刻を、推測でなく実測で決めるためのデータ集め（nwp_chart_web の check_availability.py の
      コピーを ENS 向けに調整。共通部品化しない）。
動作: 直近の初期値について、代表の予報時間（0・168・336・360h）が配信されたかを軽く確認（HEAD要求のみ・データは取らない）し、
      **最初に確認できた時刻**を logs/availability.csv に追記する。10分おきに実行する想定（launchd）。

  python check_availability.py            # 1回確認して記録（launchd から呼ぶ）
  python check_availability.py --report   # 記録を集計して、初期時刻ごとの遅れ（初期値からの経過時間）を表示

注意: 初回実行時にすでに揃っていたものは「いつ揃ったか分からない」ので記録しない（状態だけ覚える）。
      Mac がスリープしている間は確認できない（復帰後の確認時刻が記録され、遅れが大きく出る）。
      csv の「検出間隔[分]」が大きい行は精度が低い。360h が揃った時刻 = 作図に必要な最後。
"""
import argparse
import csv
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_ens as fe
import fetch_gefs as fg

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
STATE = LOG_DIR / "availability_state.json"
CSV = LOG_DIR / "availability.csv"
# モデルごとの代表の予報時間。最後の値が「作図に必要な最後」（ens=統計図は360h・天気図は168h、gefs=天気図の168h）
MODEL_STEPS = {"ens": (0, 168, 336, 360), "gefs": (0, 168)}
HOURS_BACK = 36                 # この時間より古い初期値は確認しない
HEADER = ["モデル", "初期値UTC", "FT", "検出時刻UTC", "初期値からの経過[h]", "検出間隔[分]"]


def _available(model, init, step):
    if model == "gefs":
        url = fg.mean_url(init, step)
        return fg._head_ok(url + ".idx") and fg._head_ok(url)
    url = fe.base_url(init, step)
    return fe._head_ok(url + ".index") and fe._head_ok(url + ".grib2")


def check():
    LOG_DIR.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else None
    first_run = st is None
    if first_run:
        st = {"seen": {}, "last_check": None}
    last = datetime.fromisoformat(st["last_check"]) if st.get("last_check") else None
    gap = round((now - last).total_seconds() / 60) if last else None
    rows = []
    for model, steps in MODEL_STEPS.items():
        for init in fe.candidate_inits(days_back=2):
            age_h = (now - init).total_seconds() / 3600
            if age_h < 0 or age_h > HOURS_BACK:
                continue
            for s in steps:
                key = f"{model}/{init:%Y%m%d%H}/{s}"
                if key in st["seen"] or not _available(model, init, s):
                    continue
                if first_run or not any(k.startswith(model + "/") for k in st["seen"]):
                    st["seen"][key] = "baseline"          # 初回（このモデルを記録し始めた回）に揃っていたもの
                else:
                    st["seen"][key] = now.isoformat(timespec="seconds")
                    rows.append([model, f"{init:%Y%m%d%H}", s, f"{now:%Y-%m-%d %H:%M}", f"{age_h:.2f}", gap])
    cutoff = now - timedelta(hours=HOURS_BACK + 24)
    st["seen"] = {k: v for k, v in st["seen"].items() if fe.parse_init(k.split("/")[1]) > cutoff}
    st["last_check"] = now.isoformat(timespec="seconds")
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    if rows:
        new = not CSV.exists()
        with CSV.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(HEADER)
            w.writerows(rows)
    stamp = f"{now:%Y-%m-%d %H:%M:%S}"
    if first_run:
        print(f"{stamp} 初回: 揃い済み {len(st['seen'])} 件を基準として記録（以降の新規だけ記録します）")
    else:
        for r in rows:
            print(f"{stamp} 新規: {r[0]} {r[1]} FT{r[2]} 経過 {r[4]}h（検出間隔 {r[5]}分）")
        if not rows:
            print(f"{stamp} 新規なし")


def report():
    if not CSV.exists():
        print("まだ記録がありません")
        return
    with CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"記録 {len(rows)} 件（初期値からの経過時間[h]）")
    for model, steps in MODEL_STEPS.items():
        last = str(steps[-1])
        mrows = [r for r in rows if r["モデル"] == model]
        if not mrows:
            continue
        print(f"\n■ {model}: 初期値ごとの実測（{last}h が揃った経過時間 = 作図に必要な最後）")
        by = {}
        for r in mrows:
            if r["FT"] == last:
                print(f"  {r['初期値UTC']} → {r['検出時刻UTC']} UTC 揃う（初期値から {float(r['初期値からの経過[h]']):.2f}h後, "
                      f"検出間隔 {r['検出間隔[分]']}分）")
                if r["検出間隔[分]"] in ("", "None") or int(r["検出間隔[分]"]) <= 30:
                    by.setdefault(r["初期値UTC"][-2:] + "UTC", []).append(float(r["初期値からの経過[h]"]))
        print(f"■ {model}: 初期時刻(UTC)ごとの FT{last} が揃うまでの経過時間[h]（中央値・最大・件数。検出間隔30分超は除く）")
        for hh, v in sorted(by.items()):
            print(f"  {hh}: 中央値 {statistics.median(v):.2f}h / 最大 {max(v):.2f}h / {len(v)}件")
        t = {}
        for r in mrows:
            t.setdefault(r["初期値UTC"], {})[r["FT"]] = float(r["初期値からの経過[h]"])
        for k, d in sorted(t.items()):
            if "0" in d and last in d:
                print(f"  参考 {k}: FT0 {d['0']:.2f}h → FT{last} {d[last]:.2f}h（差 {d[last] - d['0']:.2f}h）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ENS の初期値が揃う時刻を実測して記録する")
    ap.add_argument("--report", action="store_true", help="記録を集計して表示する")
    a = ap.parse_args()
    report() if a.report else check()
