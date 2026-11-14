# coding: utf-8
"""publish の単体テスト（ネットワーク不要。公開はローカルの bare リポジトリで検証）。"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish as pb


def test_parse_name():
    a = pb.parse_name("ecmwf-ens_2026111312_c1_p1_asia.png")
    assert (a["chart"], a["kind"], a["value"], a["region"], a["init"]) == ("c1", "period", 1, "asia", "2026111312")
    b = pb.parse_name("ecmwf-ens_2026111312_c2_f168_nh.png")
    assert (b["chart"], b["kind"], b["value"], b["region"]) == ("c2", "step", 168, "nh")
    c = pb.parse_name("ecmwf-ens_2026111312_c3high_p2_asia.png")
    assert c["chart"] == "c3high" and c["value"] == 2
    assert pb.parse_name("memo.png") is None


def _mk(root, init, names):
    d = root / "charts" / init
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_bytes(b"x")


def test_manifest_and_prune_keep_newest(tmp_path):
    for i in ("2026111100", "2026111112", "2026111200", "2026111212"):
        _mk(tmp_path, i, [f"ecmwf-ens_{i}_c1_p1_asia.png", "junk.txt"])
    man = pb.build_manifest(tmp_path / "charts", keep=3)
    assert [x["init"] for x in man["inits"]] == ["2026111212", "2026111200", "2026111112"]
    assert all(len(x["files"]) == 1 for x in man["inits"])          # PNG以外は載せない
    assert pb.prune(tmp_path / "charts", keep=3) == ["2026111100"]
    assert not (tmp_path / "charts" / "2026111100").exists()


def test_publish_to_local_bare_repo_keeps_single_commit(tmp_path):
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    for init in ("2026111300", "2026111312"):
        src = tmp_path / "out" / init
        src.mkdir(parents=True)
        (src / f"ecmwf-ens_{init}_c1_p1_asia.png").write_bytes(b"png")
        pb.publish(src, remote=str(bare), keep=8)
    log = subprocess.run(["git", "--git-dir", str(bare), "log", "--oneline", pb.BRANCH],
                         capture_output=True, text=True, check=True).stdout.strip().splitlines()
    assert len(log) == 1                                              # 履歴を溜めない
    files = subprocess.run(["git", "--git-dir", str(bare), "ls-tree", "-r", "--name-only", pb.BRANCH],
                           capture_output=True, text=True, check=True).stdout.split()
    assert "manifest.json" in files
    assert "charts/2026111300/ecmwf-ens_2026111300_c1_p1_asia.png" in files   # 前回分を引き継ぐ
    assert "charts/2026111312/ecmwf-ens_2026111312_c1_p1_asia.png" in files


def test_web_only_replaces_web_and_keeps_charts(tmp_path):
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    src = tmp_path / "out" / "2026111312"
    src.mkdir(parents=True)
    (src / "ecmwf-ens_2026111312_c1_p1_asia.png").write_bytes(b"png")
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("v1", encoding="utf-8")
    pb.publish(src, remote=str(bare), web_dir=web)
    (web / "index.html").write_text("v2", encoding="utf-8")
    pb.publish(None, remote=str(bare), web_dir=web)                 # 画面だけ
    show = lambda p: subprocess.run(["git", "--git-dir", str(bare), "show", f"{pb.BRANCH}:{p}"],
                                    capture_output=True, text=True, check=True).stdout
    assert show("index.html") == "v2"
    assert "ecmwf-ens_2026111312_c1_p1_asia.png" in show("manifest.json")   # 図は残っている
