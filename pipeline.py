#!/usr/bin/env python
# coding: utf-8
"""逐次集計パイプライン: 取得 → 期間平均に足し込む → GRIB2 は即削除 → 作図。

GRIB2 を残さない運用（GitHub Actions・Render 向け）。1ステップずつ一時ディレクトリに取得して読み込み、
期間平均の途中経過（メンバー別の合計）だけをメモリに持つ。ディスクに残るのは常に1ステップ分(約20MB)以下。
取得データを手元に残して試行錯誤したい場合は make_charts.py（保存したGRIB2を使う）を使う。

例: python pipeline.py --init 2026111312 --regions asia nh
    python pipeline.py            （最新の揃った初期値を自動で選ぶ）
"""
import argparse
import tempfile
import time
from pathlib import Path

import numpy as np

import charts
import climatology as cl
import fetch_ens as fe
import make_charts as mc
import stats

# 保持する範囲（全地域の crop の和集合）。全球のまま持つとメモリが約2倍になる
KEEP_LAT = (-5.0, 90.0)
C2_STEPS = (168, 240, 336)          # スパゲッティ図を作る予報時間[h]（期間平均の取得ステップに含まれる）


def _crop_lat(d, lats):
    j = np.where((lats >= KEEP_LAT[0]) & (lats <= KEEP_LAT[1]))[0]
    return d[:, j, :], lats[j]


def stream_period(init, name, steps, on_step=None, workers=fe.WORKERS):
    """steps を順に取得して読み、メンバー別の期間平均 (member, lat, lon)・lats・lons・メンバー数を返す。

    on_step(step, data, lats, lons): 各ステップを読んだ直後に呼ばれる（C2 など1時刻の図用）。
    GRIB2 は一時ディレクトリに置き、ステップごとに削除する。取得失敗のステップがあれば例外にする。
    """
    total = None
    lats = lons = None
    members = 0
    for s in steps:
        t0 = time.time()
        with tempfile.TemporaryDirectory(prefix="wsc_") as td:
            path = fe.fetch_step(init, s, name, Path(td), workers)
            if path is None:
                raise RuntimeError(f"{name} f{s:03d} の取得に失敗しました")
            d, la, lons, mem = fe.load_members(path, name)
        d, lats = _crop_lat(d, la)
        members = len(mem)
        total = d.copy() if total is None else total + d
        if on_step:
            on_step(s, d, lats, lons)
        print(f"  {name} f{s:03d}: {time.time() - t0:.1f}秒", flush=True)
    return total / len(steps), lats, lons, members


def run(init, regions, out_dir, threshold=1.0, c2_steps=C2_STEPS, workers=fe.WORKERS):
    """C1（期間1・2）・C2・C3 をまとめて作る。作成したファイルの一覧を返す。"""
    out = []

    # ---- Z500: C1（期間平均）と C2（1時刻）を同じ取得で作る
    for period in (1, 2):
        p = mc.PERIODS[period]
        steps = p["steps"]
        want = [s for s in c2_steps if s in steps]

        def c2(step, d, lats, lons):
            if step not in want:
                return
            zmean = stats.ens_mean(d)
            for region in regions:
                f = Path(out_dir) / f"ecmwf-ens_{init:%Y%m%d%H}_c2_f{step:03d}_{region}.png"
                f.parent.mkdir(parents=True, exist_ok=True)
                charts.render_c2(d, zmean, lats, lons, region=region, init=init, step=step,
                                 members=d.shape[0], source_text=mc.SOURCE, out_path=f)
                out.append(f)
                print("作成:", f, flush=True)

        x, lats, lons, members = stream_period(init, "z500", steps, on_step=c2, workers=workers)
        zmean = stats.ens_mean(x)
        clim = cl.clim_on_grid("z500", cl.valid_times(init, steps), lats, lons)
        zanom = stats.anomaly(zmean, clim)
        for region in regions:
            f = Path(out_dir) / f"ecmwf-ens_{init:%Y%m%d%H}_c1_p{period}_{region}.png"
            charts.render_c1(zmean, zanom, lats, lons, region=region, init=init, period_label=p["label"],
                             steps=steps, members=members, clim_text=cl.SOURCE_TEXT,
                             source_text=mc.SOURCE, out_path=f)
            out.append(f)
            print("作成:", f, flush=True)

        # ---- T850: C3（メンバー別の期間平均偏差 → 平均偏差と確率）
        sp, _, _, _ = stream_period(init, "sp", [steps[0]], workers=workers)
        below = stats.ens_mean(sp) < 85000.0           # 地表気圧が850hPa未満＝850hPaは地面の下
        xt, lats, lons, members = stream_period(init, "t850", steps, workers=workers)
        clim = cl.clim_on_grid("t850", cl.valid_times(init, steps), lats, lons)
        xa = stats.anomaly(xt, clim)
        amean = stats.ens_mean(xa)
        for kind, prob in (("high", stats.prob_above(xa, threshold)), ("low", stats.prob_below(xa, -threshold))):
            for region in regions:
                f = Path(out_dir) / f"ecmwf-ens_{init:%Y%m%d%H}_c3{kind}_p{period}_{region}.png"
                charts.render_c3(amean, prob, lats, lons, region=region, init=init, period_label=p["label"],
                                 steps=steps, members=members, kind=kind, threshold=threshold,
                                 clim_text=cl.SOURCE_TEXT, source_text=mc.SOURCE, out_path=f,
                                 below_ground=below)
                out.append(f)
                print("作成:", f, flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", help="YYYYMMDDHH（UTC）。省略時は最新の揃った初期値")
    ap.add_argument("--regions", nargs="+", default=["asia", "nh"], choices=list(charts.REGIONS))
    ap.add_argument("--out", default=str(mc.OUT_DIR))
    ap.add_argument("--workers", type=int, default=fe.WORKERS)
    a = ap.parse_args()
    init = fe.parse_init(a.init) if a.init else fe.find_latest_complete()
    if init is None:
        raise SystemExit("揃った初期値が見つかりません")
    print("初期値:", init, flush=True)
    t0 = time.time()
    files = run(init, a.regions, a.out, workers=a.workers)
    print(f"完了: {len(files)}枚 {time.time() - t0:.0f}秒")
