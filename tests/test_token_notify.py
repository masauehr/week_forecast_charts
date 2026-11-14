# coding: utf-8
"""ops/token_expiry_notify の単体テスト（送信はしない）。"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
import token_expiry_notify as tn

EXP = datetime(2027, 2, 8, 1, 45, tzinfo=timezone.utc)


def test_level_boundaries():
    assert tn.level_for(EXP - timedelta(days=30), EXP) is None
    assert tn.level_for(EXP - timedelta(days=14), EXP) == 14
    assert tn.level_for(EXP - timedelta(days=6, hours=1), EXP) == 7
    assert tn.level_for(EXP - timedelta(hours=5), EXP) == 1
    assert tn.level_for(EXP + timedelta(seconds=1), EXP) == "expired"


def test_decide_notifies_once_per_level_and_resets_on_renewal():
    now = EXP - timedelta(days=13)
    lvl, send = tn.decide(now, EXP, {})
    assert (lvl, send) == (14, True)
    state = {"expiry": tn.iso_z(EXP), "level": 14}
    assert tn.decide(now, EXP, state) == (14, False)                       # 同じ段階は再送しない
    new_exp = EXP + timedelta(days=90)                                      # 更新で期限が変われば状態をリセット
    assert tn.decide(new_exp - timedelta(days=13), new_exp, state) == (14, True)


def test_message_mentions_guide_and_project():
    text = tn.message(EXP - timedelta(days=2), EXP, 2)
    assert "week_to_season_charts" in text and "CRON_JOB_ORG.md" in text
