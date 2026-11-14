# coding: utf-8
"""アンサンブル平均の天気図まわりの単体テスト（ネットワーク不要）。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_gefs as fg
import mean_charts as mc


def test_window_parse():
    assert fg._window("18-24 hour acc fcst") == 6
    assert fg._window("0-12 hour ave fcst") == 12
    assert fg._window("24 hour fcst") is None


def test_urls():
    t = fg.parse_init("2026111312")
    assert fg.mean_url(t, 24).endswith("/gefs.20261113/12/atmos/pgrb2ap5/geavg.t12z.pgrb2a.0p50.f024")
    assert fg.member_url(t, 24, "c00").endswith("/pgrb2bp5/gec00.t12z.pgrb2b.0p50.f024")
    assert fg.member_url(t, 24, "p07").endswith("/pgrb2bp5/gep07.t12z.pgrb2b.0p50.f024")


def _idx(rows):
    out, off = [], 0
    for n, (var, lev, fc) in enumerate(rows, 1):
        out.append((n, off, 100, var, lev, fc))
        off += 100
    return out


def test_select_records_picks_needed_and_shortest_window():
    idx = _idx([
        ("HGT", "500 mb", "24 hour fcst"), ("HGT", "300 mb", "24 hour fcst"),      # 300hPaは除外
        ("TMP", "850 mb", "24 hour fcst"), ("TMP", "2 m above ground", "24 hour fcst"),
        ("RH", "700 mb", "24 hour fcst"), ("RH", "2 m above ground", "24 hour fcst"),   # 2m RH は不要
        ("UGRD", "10 m above ground", "24 hour fcst"), ("PRMSL", "mean sea level", "24 hour fcst"),
        ("PRES", "surface", "24 hour fcst"),
        ("APCP", "surface", "0-24 hour acc fcst"), ("APCP", "surface", "18-24 hour acc fcst"),
        ("TCDC", "entire atmosphere", "18-24 hour ave fcst"),
    ])
    got = [(r[3], r[4], r[5]) for r in fg.select_records(idx)]
    assert ("HGT", "500 mb", "24 hour fcst") in got and ("HGT", "300 mb", "24 hour fcst") not in got
    assert ("RH", "2 m above ground", "24 hour fcst") not in got
    assert ("APCP", "surface", "18-24 hour acc fcst") in got and ("APCP", "surface", "0-24 hour acc fcst") not in got
    assert len(got) == 9


def _F(levels):
    z = np.zeros((2, 2), dtype="float32")
    return {"p": {lv: {"gh": z, "t": z, "u": z, "v": z, "r": z, "w": z} for lv in levels}}


def test_charts_for_depends_on_available_levels():
    ks = mc.charts_for(_F([925, 850, 700, 500, 200]))            # GEFSの平均（300hPaの気温・湿度が無い）
    assert "jet300" not in ks and "t300" not in ks
    assert {"t850", "ept850", "t700", "z500", "jet200", "surf", "tenki"} <= set(ks)
    assert "jet300" in mc.charts_for(_F([925, 850, 700, 500, 300, 200]))   # ENSは300hPaも持つ


def test_850_is_split_into_two_charts_without_ssi():
    assert "t850" in mc.CHARTS and "ept850" in mc.CHARTS
    assert "SSI" not in mc.CHARTS["ept850"]["label"]


def test_warm_up_loads_every_region(monkeypatch):
    seen = []
    monkeypatch.setattr(mc, "base_lines", lambda region, proj: seen.append(region))
    monkeypatch.setattr(mc, "make_projection", lambda region: (None, None))
    mc.warm_up()
    assert seen == list(mc.REGIONS)
