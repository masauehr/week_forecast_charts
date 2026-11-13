# coding: utf-8
"""fetch_ens の単体テスト（ネットワーク不要）。"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_ens as fe


def _row(param, levtype, level, number, off, ln, typ="pf"):
    d = {"type": typ, "param": param, "levtype": levtype, "number": str(number),
         "_offset": off, "_length": ln}
    if level is not None:
        d["levelist"] = level
    return d


def test_parse_init():
    t = fe.parse_init("2026111312")
    assert t == datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def test_base_url():
    t = fe.parse_init("2026111312")
    assert fe.base_url(t, 120) == ("https://data.ecmwf.int/forecasts/20261113/12z/ifs/0p25/enfo/"
                                   "20261113120000-120h-enfo-ef")


def test_select_rows_picks_only_target_and_sorts():
    rows = [
        _row("gh", "pl", "500", 2, 300, 10),
        _row("t", "pl", "850", 1, 100, 10),
        _row("gh", "pl", "850", 1, 50, 10),      # 別の面 → 除外
        _row("msl", "sfc", None, 1, 200, 10),
        _row("gh", "pl", "500", 1, 0, 10, typ="cf"),   # コントロールは除外
    ]
    got = fe.select_rows(rows, ("z500", "t850", "msl"))
    assert [(n, x["_offset"]) for n, x in got] == [("t850", 100), ("msl", 200), ("z500", 300)]


def test_merge_ranges():
    assert fe.merge_ranges([(0, 10), (10, 5), (20, 5)]) == [(0, 15), (20, 5)]
    assert fe.merge_ranges([(30, 5), (0, 10)]) == [(0, 10), (30, 5)]


def test_candidate_inits_only_00_12():
    assert all(t.hour in (0, 12) for t in fe.candidate_inits(2))


def test_step_path_is_per_variable():
    t = fe.parse_init("2026111312")
    a = fe.step_path(t, 24, "z500", Path("/x"))
    b = fe.step_path(t, 24, "t850", Path("/x"))
    assert a != b and a.name == "f024_z500.grib2" and b.name == "f024_t850.grib2"
