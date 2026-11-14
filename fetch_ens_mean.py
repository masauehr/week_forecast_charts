#!/usr/bin/env python
# coding: utf-8
"""ECMWF ENS（50メンバー）の「アンサンブル平均」を天気図用の辞書 F にする。

ENS には平均のファイルが無いため、必要な変数ごとに 50メンバー分を範囲取得（fetch_ens）して平均し、すぐ捨てる
（メモリに残るのは平均場だけ。GRIB2 は一時ディレクトリに置いて削除）。
F の形式は nwp_chart_web の load_fields と同じ（mean_charts.py がそのまま使える）。fetch_gefs.load_F と同形式。

変数（1ステップあたり約38フィールド・各約20MB）:
  気圧面 925/850/700/500/300/200hPa × gh,t,u,v,r ＋ 700hPa の w ＋ 地上 msl,sp,10u,10v,2t,tcc,tp
降水(tp)は初期時刻からの積算なので、12時間前との差を 12 で割って mm/h にする（rr_h=12）。
"""
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

import fetch_ens as fe

PLEVELS = (925, 850, 700, 500, 300, 200)
PL_VARS = ("gh", "t", "u", "v", "r")
STEP_H = 12                                   # 降水の差分に使う間隔（週間予報用は12時間毎）
FIELD_WORKERS = 4                             # 同時に取る変数の数（各変数の内部でも並列Range取得）
RANGE_WORKERS = 8


def register_vars():
    """fetch_ens.VARS に、天気図用の変数を登録する（名前 → (索引のparam, levtype, 面, pygribのshortName, level)）。"""
    for lv in PLEVELS:
        for p in PL_VARS:
            fe.VARS.setdefault(f"{p}{lv}", (p, "pl", str(lv), p, lv))
    fe.VARS.setdefault("w700", ("w", "pl", "700", "w", 700))
    fe.VARS.setdefault("u10", ("10u", "sfc", None, "10u", 0))
    fe.VARS.setdefault("v10", ("10v", "sfc", None, "10v", 0))
    fe.VARS.setdefault("t2", ("2t", "sfc", None, "2t", 0))
    fe.VARS.setdefault("tcc", ("tcc", "sfc", None, "tcc", 0))
    fe.VARS.setdefault("tp", ("tp", "sfc", None, "tp", 0))


register_vars()


def field_names(step: int):
    names = [f"{p}{lv}" for lv in PLEVELS for p in PL_VARS] + ["w700", "msl", "sp", "u10", "v10", "t2", "tcc"]
    if step > 0:
        names.append("tp")
    return names


def _mean(init: datetime, step: int, name: str, workers: int = RANGE_WORKERS):
    """変数 name の全メンバー平均 (lat, lon) と lats, lons を返す。"""
    with tempfile.TemporaryDirectory(prefix="wsc_ens_") as td:
        path = fe.fetch_step(init, step, name, Path(td), workers)
        if path is None:
            raise RuntimeError(f"{name} f{step:03d} の取得に失敗しました")
        d, lats, lons, _ = fe.load_members(path, name)
    return d.mean(axis=0), lats, lons


def build_F(init: datetime, step: int, field_workers: int = FIELD_WORKERS, workers: int = RANGE_WORKERS):
    """初期値 init・予報時間 step[h] の ENS 平均場を F 辞書で返す。"""
    names = field_names(step)
    prev_tp = step - STEP_H if step > STEP_H else None        # step==12 なら前の積算は0
    jobs = [(step, n) for n in names]
    if step > 0 and prev_tp is not None:
        jobs.append((prev_tp, "tp"))
    with ThreadPoolExecutor(field_workers) as ex:
        res = list(ex.map(lambda j: (j, _mean(init, j[0], j[1], workers)), jobs))
    M, lats, lons = {}, None, None
    for (st, n), (m, la, lo) in res:
        M[(st, n)] = m
        lats, lons = la, lo
    F = {"lats": lats, "lons": lons, "rr": None, "rr_h": STEP_H}
    F["msl"] = M[(step, "msl")] / 100.0
    F["sp"] = M[(step, "sp")] / 100.0
    F["u10"], F["v10"] = M[(step, "u10")], M[(step, "v10")]
    F["t2"] = M[(step, "t2")] - 273.15
    F["tcc"] = M[(step, "tcc")] * 100.0                        # 0-1 → %
    if step > 0:
        prev = M[(prev_tp, "tp")] if prev_tp is not None else 0.0
        F["rr"] = ((M[(step, "tp")] - prev) * 1000.0 / STEP_H).clip(min=0)   # m の積算 → mm/h
    F["p"] = {}
    for lv in PLEVELS:
        F["p"][lv] = {"gh": M[(step, f"gh{lv}")], "t": M[(step, f"t{lv}")] - 273.15,
                      "u": M[(step, f"u{lv}")], "v": M[(step, f"v{lv}")], "r": M[(step, f"r{lv}")],
                      "w": (M[(step, "w700")] * 36.0 if lv == 700 else np.zeros_like(M[(step, f"t{lv}")]))}
    return F
