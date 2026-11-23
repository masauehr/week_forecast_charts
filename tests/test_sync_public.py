# coding: utf-8
"""sync_public の単体テスト（ネットワーク不要。一時ディレクトリの git リポジトリで取り込みを検証）。"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_public as sp


def _git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path):
    """公開ブランチ相当（charts/・maps/output/）を持つ git リポジトリを作り、先頭コミットを返す。"""
    r = tmp_path / "pub"
    for rel in ("charts/2026112000/a.png", "charts/2026112012/a.png",
                "maps/output/ens/2026112012/asia/x_000.png", "maps/output/gefs/2026112012/asia/x_000.png"):
        f = r / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    _git(r, "init", "-q")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@example.com", "add", "-A")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "m")
    return r, subprocess.run(["git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True).stdout.strip()


def test_sync_takes_public_only_and_prunes(tmp_path, monkeypatch):
    pub, tip = _repo(tmp_path)
    out = tmp_path / "out"
    (out / "maps" / "gsm" / "2026111000").mkdir(parents=True)          # GSM はローカル専用: 触れない
    (out / "maps" / "ens" / "2026111900").mkdir(parents=True)          # 公開側の最古より古い: 消える
    monkeypatch.setattr(sp, "ROOT", pub)
    monkeypatch.setattr(sp, "OUT", out)
    public, got = sp.sync(tip)
    assert got == 4                                                    # 統計図2＋ens1＋gefs1
    assert (out / "2026112012" / "a.png").exists()
    assert (out / "maps" / "ens" / "2026112012" / "asia" / "x_000.png").exists()
    assert sp.prune(public) == 1
    assert not (out / "maps" / "ens" / "2026111900").exists()
    assert (out / "maps" / "gsm" / "2026111000").exists()              # GSM は残る
    assert sp.sync(tip)[1] == 0                                        # 2回目は取り直さない


def test_prune_does_nothing_without_public_list(tmp_path, monkeypatch):
    out = tmp_path / "out"
    (out / "2026111000").mkdir(parents=True)
    monkeypatch.setattr(sp, "OUT", out)
    assert sp.prune({"stat": []}) == 0
    assert (out / "2026111000").exists()
