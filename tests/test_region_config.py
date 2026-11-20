# coding: utf-8
"""地域の設定ファイル（沖縄周辺を別の地域に入れ替える）のテスト（ネットワーク不要）。"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mean_charts as mc


def _copy():
    return {k: dict(v) for k, v in mc.REGIONS.items()}, dict(mc.LABEL_ZONES)


def test_region_zone_names_exist():
    """地域の label_zones は、すべて LABEL_ZONES に定義がある。"""
    for name, r in mc.REGIONS.items():
        for z in r.get("label_zones", ()):
            assert z in mc.LABEL_ZONES, (name, z)


def test_example_config_is_valid():
    """同梱の設定例は、そのまま反映できる。"""
    cfg = json.loads((Path(__file__).resolve().parents[1] / "region_config.example.json").read_text(encoding="utf-8"))
    regs, zones = _copy()
    assert mc.apply_region_config(cfg, regs, zones) == ["okinawa"]
    assert regs["okinawa"]["label"] == "九州周辺"


def test_region_config_swaps_okinawa():
    """設定で沖縄周辺の名前・範囲を入れ替えられ、キーは変わらない。書かなかった項目は元のまま。"""
    regs, zones = _copy()
    cfg = {"label_zones": {"z": [128, 134, 30, 35]},
           "regions": {"okinawa": {"label": "九州周辺", "center": [131, 33], "width_deg": 14,
                                   "bbox": [115, 148, 20, 46], "label_zones": ["z"]}}}
    assert mc.apply_region_config(cfg, regs, zones) == ["okinawa"]
    assert regs["okinawa"]["label"] == "九州周辺" and regs["okinawa"]["center"] == (131.0, 33.0)
    assert regs["okinawa"]["label_zones"] == ("z",) and zones["z"] == (128.0, 134.0, 30.0, 35.0)
    assert regs["okinawa"]["coast"] == "10m" and regs["okinawa"]["zoom"] == 3


def test_region_config_rejects_bad_input():
    """不正な設定は ValueError で、地域定義は変わらない。"""
    base = {"label": "x", "center": [131, 33], "width_deg": 14, "bbox": [115, 148, 20, 46]}
    bads = [
        {"regions": {"new_region": base}},                                  # 地域は増やせない
        {"regions": {"okinawa": {**base, "bbox": [115, 148, 20, 95]}}},    # データ範囲の外
        {"regions": {"okinawa": {**base, "foo": 1}}},                      # 未知の項目
        {"regions": {"okinawa": {**base, "label_zones": ["nothing"]}}},    # 未定義のゾーン
        {"regions": {"okinawa": {**base, "width_deg": -1}}},               # 幅が不正
        {"regions": {"okinawa": {**base, "center": [131]}}},               # 中心が不正
    ]
    for cfg in bads:
        regs, zones = _copy()
        with pytest.raises(ValueError):
            mc.apply_region_config(cfg, regs, zones)
        assert regs == _copy()[0]


def test_region_config_missing_file_is_noop(tmp_path):
    assert mc.load_region_config(tmp_path / "none.json") == []


def test_region_config_broken_file_is_ignored(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json", encoding="utf-8")
    assert mc.load_region_config(p) == []


def test_view_uses_swapped_bbox():
    """入れ替えた bbox で切り出される（View が REGIONS を参照している）。"""
    F = {"lats": np.arange(-90, 90.1, 1.0), "lons": np.arange(0, 360, 1.0)}
    old = mc.REGIONS["okinawa"]
    try:
        mc.REGIONS["okinawa"] = dict(old, bbox=(118.0, 145.0, 24.0, 42.0))
        V = mc.View(F, "okinawa")
        assert V.lons[0] == 118 and V.lons[-1] == 145 and V.lats[0] == 24 and V.lats[-1] == 42
    finally:
        mc.REGIONS["okinawa"] = old
