#!/usr/bin/env python
# coding: utf-8
"""平年値（気候値）の読み込みと偏差の計算。

平年値: NOAA PSL の NCEP/NCAR 再解析 日別長期平均 1991–2020（2.5°・365日・うるう日なし）。
  https://downloads.psl.noaa.gov/Datasets/ncep.reanalysis.derived/{pressure,surface}/{hgt,air,slp}.day.ltm.1991-2020.nc
  Kalnay et al. 1996。NOAA PSL のデータ。図には出典と期間を必ず明記する（CLAUDE.md）。
基準期間は気象庁平年値(1991–2020)と同じ。ただし再解析と予報モデルの間に系統差（Z500で数gpm程度）がありうる。
予報の格子(0.25°)へは双線形補間（経度は周期）で合わせる。
"""
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

CLIM_DIR = Path(__file__).resolve().parent / "data" / "clim"
SOURCE_TEXT = "NCEP/NCAR Reanalysis daily long-term mean 1991-2020 (NOAA PSL)"

# 変数名 -> (ファイル名, 変数名, 気圧面 or None, 単位換算の係数, 単位換算のオフセット)
# fetch_ens.VARS と同じ名前を使う（z500=gpm・t850=K・msl=Pa。再解析の単位も同じ）
CLIM_VARS = {
    "z500": ("hgt.day.ltm.1991-2020.nc", "hgt", 500.0),
    "t850": ("air.day.ltm.1991-2020.nc", "air", 850.0),
    "msl": ("slp.day.ltm.1991-2020.nc", "slp", None),
}

_CACHE = {}


def doy_index(t: datetime) -> int:
    """日付 → 平年値の日インデックス（0..364）。うるう日(2/29)は2/28に寄せる。"""
    d = t.timetuple().tm_yday
    if (t.year % 4 == 0 and (t.year % 100 != 0 or t.year % 400 == 0)) and t.month >= 3:
        d -= 1                       # うるう年の3月以降は1日ずらして365日暦に合わせる
    elif t.month == 2 and t.day == 29:
        d = 59                       # 2/29 → 2/28（0始まりで 58 → 下で -1）
    return d - 1


def load_clim(name: str, clim_dir: Path = CLIM_DIR):
    """平年値を (data[365, lat, lon], lats(昇順), lons(0..357.5)) で返す。結果はキャッシュ。"""
    key = (name, str(clim_dir))
    if key in _CACHE:
        return _CACHE[key]
    import xarray as xr
    fname, var, level = CLIM_VARS[name]
    ds = xr.open_dataset(Path(clim_dir) / fname, decode_times=False)
    v = ds[var]
    if level is not None:
        v = v.sel(level=level)
    arr = np.asarray(v.values, dtype="float32")        # (365, lat, lon)
    lats = np.asarray(ds["lat"].values, dtype="float64")
    lons = np.asarray(ds["lon"].values, dtype="float64")
    ds.close()
    if lats[0] > lats[-1]:                             # 緯度を昇順に
        arr = arr[:, ::-1, :]
        lats = lats[::-1]
    _CACHE[key] = (arr, lats, lons)
    return _CACHE[key]


def clim_mean(name: str, times, clim_dir: Path = CLIM_DIR):
    """時刻のリストに対応する平年値を平均した 2.5° 格子 (lat, lon) と lats, lons を返す。"""
    arr, lats, lons = load_clim(name, clim_dir)
    idx = [doy_index(t) for t in times]
    return arr[idx].mean(axis=0), lats, lons


def regrid(field, src_lats, src_lons, dst_lats, dst_lons):
    """双線形補間（経度は周期）。field は (lat, lon)。dst は昇順の 1 次元。"""
    # 経度の周期性のため、東端に 360° の列を足す
    f = np.concatenate([field, field[:, :1]], axis=1)
    lo = np.concatenate([src_lons, [src_lons[0] + 360.0]])
    # 緯度方向
    la_i = np.clip(np.searchsorted(src_lats, dst_lats) - 1, 0, len(src_lats) - 2)
    la_w = np.clip((dst_lats - src_lats[la_i]) / (src_lats[la_i + 1] - src_lats[la_i]), 0.0, 1.0)
    # 経度方向（dst の経度を 0..360 に）
    dl = np.mod(dst_lons, 360.0)
    lo_i = np.clip(np.searchsorted(lo, dl, side="right") - 1, 0, len(lo) - 2)
    lo_w = (dl - lo[lo_i]) / (lo[lo_i + 1] - lo[lo_i])
    a = f[la_i][:, lo_i]
    b = f[la_i][:, lo_i + 1]
    c = f[la_i + 1][:, lo_i]
    d = f[la_i + 1][:, lo_i + 1]
    lw = lo_w[None, :]
    aw = la_w[:, None]
    return ((a * (1 - lw) + b * lw) * (1 - aw) + (c * (1 - lw) + d * lw) * aw).astype("float32")


def clim_on_grid(name: str, times, dst_lats, dst_lons, clim_dir: Path = CLIM_DIR):
    """時刻リストの平年値（平均）を予報格子 (dst_lats, dst_lons) に補間して返す。"""
    m, la, lo = clim_mean(name, times, clim_dir)
    return regrid(m, la, lo, np.asarray(dst_lats, dtype="float64"), np.asarray(dst_lons, dtype="float64"))


def valid_times(init: datetime, steps):
    """初期値とステップ[h] → 有効時刻のリスト。"""
    return [init + timedelta(hours=int(s)) for s in steps]
