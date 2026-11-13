# coding: utf-8
"""climatology の単体テスト（ネットワーク・平年値ファイル不要）。"""
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import climatology as cl


def test_doy_index_normal_year():
    assert cl.doy_index(datetime(2026, 1, 1)) == 0
    assert cl.doy_index(datetime(2026, 12, 31)) == 364
    assert cl.doy_index(datetime(2026, 3, 1)) == 59


def test_doy_index_leap_year_aligns_with_365_calendar():
    assert cl.doy_index(datetime(2028, 2, 28)) == 58
    assert cl.doy_index(datetime(2028, 2, 29)) == 58      # 2/29 は 2/28 に寄せる
    assert cl.doy_index(datetime(2028, 3, 1)) == 59       # 平年の3/1と同じ
    assert cl.doy_index(datetime(2028, 12, 31)) == 364


def test_regrid_reproduces_linear_field():
    src_lats = np.arange(-90, 90.1, 2.5)
    src_lons = np.arange(0, 360, 2.5)
    la, lo = np.meshgrid(src_lats, src_lons, indexing="ij")
    f = (la * 2.0).astype("float32")                       # 緯度だけの線形
    dst_lats = np.array([-10.1, 0.0, 33.3])
    dst_lons = np.array([0.0, 100.3, 359.9])
    out = cl.regrid(f, src_lats, src_lons, dst_lats, dst_lons)
    assert np.allclose(out, (dst_lats * 2.0)[:, None] * np.ones((1, 3)), atol=1e-3)


def test_regrid_is_periodic_in_longitude():
    src_lats = np.array([0.0, 2.5])
    src_lons = np.arange(0, 360, 2.5)
    f = np.zeros((2, 144), dtype="float32")
    f[:, 0] = 10.0                                         # 経度0度だけ10
    out = cl.regrid(f, src_lats, src_lons, np.array([0.0]), np.array([358.75]))
    assert np.isclose(out[0, 0], 5.0, atol=1e-4)           # 357.5(0) と 360(=0度, 10) の中点
