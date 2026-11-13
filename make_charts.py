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
        path = Path(data_dir) / f"{init:%Y%m%d%H}" / f"f{s:03d}.grib2"
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", required=True, help="YYYYMMDDHH（UTC）")
    ap.add_argument("--period", type=int, choices=sorted(PERIODS), default=1)
    ap.add_argument("--regions", nargs="+", default=["asia", "nh"], choices=list(charts.REGIONS))
    a = ap.parse_args()
    build_c1(fe.parse_init(a.init), a.period, a.regions)
