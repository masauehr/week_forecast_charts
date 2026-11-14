#!/usr/bin/env python
# coding: utf-8
"""手元（ローカル）で、公開サイトと同じ構成で図を閲覧するための簡易サーバー。

  python serve_local.py            → http://127.0.0.1:8803/ （統計図）、/maps/ （天気図 標準版）、/maps/board/ （画用紙版）

手元の output/ にある図をそのまま表示する（GRIB2 の取得や作図はしない）。先に図を作っておく:
  統計図:   python pipeline.py [--init YYYYMMDDHH]                  → output/<初期値>/
  天気図:   python mean_pipeline.py --model gefs|ens [--init ...]   → output/maps/<model>/<初期値>/ ＋ manifest.json
公開サイト（GitHub Pages）と同じファイル配置になるよう、_site/ にシンボリックリンクを張る（_site/ は git 除外）。
127.0.0.1 だけで待ち受ける（外部には公開しない）。止めるときは Ctrl+C。
将来、ローカル専用の GSM（決定論）を足すときも、この仕組みで見られるようにする（公開サイトには載せない）。
"""
import argparse
import http.server
import json
import os
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "_site"


def _link(dst: Path, src: Path):
    """dst を src へのシンボリックリンクにする（既にあれば張り直す）。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        if dst.is_symlink():
            dst.unlink()
        else:
            return
    os.symlink(src, dst)


def build_site():
    """_site/ に公開サイトと同じ構成を作る。作った内容の説明（文字列のリスト）を返す。"""
    notes = []
    SITE.mkdir(exist_ok=True)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    # 統計図: web/* をルートに、output/ を charts/ に（manifest.json は手元のフォルダから作る）
    for f in (ROOT / "web").iterdir():
        if f.is_file():
            _link(SITE / f.name, f)
    _link(SITE / "charts", out)
    sys.path.insert(0, str(ROOT))
    import publish
    man = publish.build_manifest(out, keep=publish.KEEP_DEFAULT)
    (SITE / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    notes.append(f"統計図: 初期値 {[i['init'] for i in man['inits']] or 'なし（python pipeline.py で作る）'}")
    # 天気図: maps_web/* を maps/ に、output/maps/ を maps/output/ に
    mw = ROOT / "maps_web"
    for f in mw.iterdir():
        _link(SITE / "maps" / f.name, f)
    (out / "maps").mkdir(exist_ok=True)
    _link(SITE / "maps" / "output", out / "maps")
    mf = out / "maps" / "manifest.json"
    if mf.exists():
        m = json.loads(mf.read_text(encoding="utf-8"))
        notes.append("天気図: " + (", ".join(f"{k} {[i['init'] for i in v['inits']]}" for k, v in m["models"].items()) or "なし"))
    else:
        notes.append("天気図: なし（python mean_pipeline.py --model gefs で作る）")
    return notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8803)
    a = ap.parse_args()
    for n in build_site():
        print(n)
    handler = lambda *args, **kw: http.server.SimpleHTTPRequestHandler(*args, directory=str(SITE), **kw)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", a.port), handler) as srv:
        base = f"http://127.0.0.1:{a.port}"
        print(f"\n起動しました（Ctrl+C で停止）\n  統計図          {base}/\n  天気図 標準版   {base}/maps/\n  天気図 画用紙版 {base}/maps/board/")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n停止しました")


if __name__ == "__main__":
    main()
