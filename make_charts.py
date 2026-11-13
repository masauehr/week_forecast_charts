#!/usr/bin/env python
# coding: utf-8
"""CLI: 取得済みの ECMWF ENS から C1（Z500 平均と平年偏差）を作る。

例: python make_charts.py --init 2026111312 --period 1 --regions asia nh
期間: 1=予報24〜168時間（約1〜7日）、2=192〜336時間（約8〜14日）。12時間間隔の時刻を平均する。
"""
import argparse
from pathlib import Path

import numpy as np

import charts
import climatology as cl
import fetch_ens as fe
import stats

PERIODS = {
    1: dict(label="予報1〜7日目", steps=list(range(24, 169, 12))),
    2: dict(label="予報8〜14日目", steps=list(range(192, 337, 12))),
}
OUT_DIR = Path(__file__).resolve().parent / "output"
SOURCE = "ECMWF Open Data (CC BY 4.0) を加工して作成"


def build_c1(init, period, regions, data_dir=fe.DEFAULT_DATA_DIR, out_dir=OUT_DIR):
    p = PERIODS[period]
    steps = p["steps"]
    fields, lats, lons, members = [], None, None, None
    for s in steps:
        path = fe.step_path(init, s, "z500", data_dir)
        if not path.exists():
            raise FileNotFoundError(f"{path} がありません。fetch_ens.py --steps {s} --vars z500 で取得してください")
        d, lats, lons, members = fe.load_members(path, "z500")
        fields.append(d)
    x = stats.period_mean(fields)                       # (member, lat, lon)
    zmean = stats.ens_mean(x)
    clim = cl.clim_on_grid("z500", cl.valid_times(init, steps), lats, lons)
    zanom = stats.anomaly(zmean, clim)
    out = []
    for region in regions:
        f = Path(out_dir) / f"ecmwf-ens_{init:%Y%m%d%H}_c1_p{period}_{region}.png"
        f.parent.mkdir(parents=True, exist_ok=True)
        charts.render_c1(zmean, zanom, lats, lons, region=region, init=init, period_label=p["label"],
                         steps=steps, members=len(members), clim_text=cl.SOURCE_TEXT,
                         source_text=SOURCE, out_path=f)
        out.append(f)
        print("作成:", f)
    return out


def build_c2(init, steps, regions, data_dir=fe.DEFAULT_DATA_DIR, out_dir=OUT_DIR):
    """C2 スパゲッティ図（1時刻ごと）。Z500 の該当ステップが取得済みである必要がある。"""
    out = []
    for s in steps:
        path = fe.step_path(init, s, "z500", data_dir)
        if not path.exists():
            raise FileNotFoundError(f"{path} がありません。fetch_ens.py --steps {s} --vars z500 で取得してください")
        d, lats, lons, members = fe.load_members(path, "z500")
        zmean = stats.ens_mean(d)
        for region in regions:
            f = Path(out_dir) / f"ecmwf-ens_{init:%Y%m%d%H}_c2_f{s:03d}_{region}.png"
            f.parent.mkdir(parents=True, exist_ok=True)
            charts.render_c2(d, zmean, lats, lons, region=region, init=init, step=s, members=len(members),
                             source_text=SOURCE, out_path=f)
            out.append(f)
            print("作成:", f)
    return out


def build_c3(init, period, regions, threshold=1.0, data_dir=fe.DEFAULT_DATA_DIR, out_dir=OUT_DIR):
    """C3: T850 の期間平均偏差（アンサンブル平均）と、偏差が ±threshold℃を超えるメンバーの割合。"""
    p = PERIODS[period]
    steps = p["steps"]
    fields, lats, lons, members = [], None, None, None
    for s in steps:
        path = fe.step_path(init, s, "t850", data_dir)
        if not path.exists():
            raise FileNotFoundError(f"{path} がありません。fetch_ens.py --steps {s} --vars t850 で取得してください")
        d, lats, lons, members = fe.load_members(path, "t850")
        fields.append(d)
    sp_path = fe.fetch_step(init, steps[0], "sp", data_dir)
    sp, _, _, _ = fe.load_members(sp_path, "sp")
    below = stats.ens_mean(sp) < 85000.0                # 850hPaが地面より下の格子
    x = stats.period_mean(fields)                       # (member, lat, lon) [K]
    clim = cl.clim_on_grid("t850", cl.valid_times(init, steps), lats, lons)
    xa = stats.anomaly(x, clim)                         # メンバーごとの期間平均偏差
    amean = stats.ens_mean(xa)
    out = []
    for kind, prob in (("high", stats.prob_above(xa, threshold)), ("low", stats.prob_below(xa, -threshold))):
        for region in regions:
            f = Path(out_dir) / f"ecmwf-ens_{init:%Y%m%d%H}_c3{kind}_p{period}_{region}.png"
            f.parent.mkdir(parents=True, exist_ok=True)
            charts.render_c3(amean, prob, lats, lons, region=region, init=init, period_label=p["label"],
                             steps=steps, members=len(members), kind=kind, threshold=threshold,
                             clim_text=cl.SOURCE_TEXT, source_text=SOURCE, out_path=f, below_ground=below)
            out.append(f)
            print("作成:", f)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", required=True, help="YYYYMMDDHH（UTC）")
    ap.add_argument("--chart", choices=["c1", "c2", "c3"], default="c1")
    ap.add_argument("--period", type=int, choices=sorted(PERIODS), default=1, help="c1・c3 用")
    ap.add_argument("--steps", type=int, nargs="+", default=[168, 240, 336], help="c2 用（予報時間[h]）")
    ap.add_argument("--regions", nargs="+", default=["asia", "nh"], choices=list(charts.REGIONS))
    a = ap.parse_args()
    if a.chart == "c1":
        build_c1(fe.parse_init(a.init), a.period, a.regions)
    elif a.chart == "c2":
        build_c2(fe.parse_init(a.init), a.steps, a.regions)
    else:
        build_c3(fe.parse_init(a.init), a.period, a.regions)
