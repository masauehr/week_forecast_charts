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
import subprocess
import sys
import threading
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
    if any(p.is_dir() for p in (out / "maps").iterdir()):     # 画像があれば manifest を手元の画像から作り直す（作図が途中で止まった場合の取りこぼし対策）
        import maps_manifest
        maps_manifest.write_manifest(out / "maps")
    if mf.exists():
        m = json.loads(mf.read_text(encoding="utf-8"))
        notes.append("天気図: " + (", ".join(f"{k} {[i['init'] for i in v['inits']]}" for k, v in m["models"].items()) or "なし"))
    else:
        notes.append("天気図: なし（python mean_pipeline.py --model gefs で作る）")
    return notes


# ---------- 同期ジョブ（画面の「同期」ボタン用。サーバープロセス内で1つだけ）
LOG_FILE = ROOT / "logs" / "sync_ui.log"
_job = {"proc": None, "rc": None, "rebuilt": True}
_job_lock = threading.Lock()


def start_sync():
    """sync_public.py を裏で起動する。実行中なら起動せず False。"""
    with _job_lock:
        p = _job["proc"]
        if p is not None and p.poll() is None:
            return False
        LOG_FILE.parent.mkdir(exist_ok=True)
        f = open(LOG_FILE, "w", encoding="utf-8")        # 毎回上書き（最新の1回分だけ見せる）
        _job["proc"] = subprocess.Popen([sys.executable, "-u", str(ROOT / "sync_public.py"), "--force"],
                                        cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        _job["rc"] = None
        _job["rebuilt"] = False
        return True


def job_status():
    with _job_lock:
        p = _job["proc"]
        running = p is not None and p.poll() is None
        if p is not None and not running:
            _job["rc"] = p.returncode
            if not _job["rebuilt"]:                       # 終わったら _site の manifest を作り直す（画面の再読み込みで新しい図が出る）
                _job["rebuilt"] = True
                try:
                    build_site()
                except Exception as e:
                    print("manifest の作り直しに失敗:", e, file=sys.stderr)
        tail = []
        if LOG_FILE.exists():
            tail = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
        return {"running": running, "rc": _job["rc"], "log": tail}


class Handler(http.server.SimpleHTTPRequestHandler):
    """静的配信に、同期用の API（/api/status・/api/sync。ローカル・同一Originのみ）を足す。"""

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _same_origin(self):
        """他サイトのページからの POST を拒む（Origin があれば Host と一致すること）。"""
        o = self.headers.get("Origin")
        return o is None or o.split("://", 1)[-1] == self.headers.get("Host")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.endswith("/api/status"):
            return self._json(200, job_status())
        if "/api/" in path:
            return self._json(404, {"error": "未対応のAPIです"})
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if not self._same_origin():
            return self._json(403, {"error": "同一Originからのみ実行できます"})
        if path.endswith("/api/sync"):
            return self._json(200, {"started": start_sync()})
        return self._json(404, {"error": "未対応のAPIです"})

    def end_headers(self):
        # 画面（html/js/css）と manifest は毎回取り直させる（手元で画面を直しても古い版が残らないように）。画像はキャッシュしてよい
        if self.path.split("?", 1)[0].endswith((".json", ".js", ".css", ".html", "/")):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8803)
    a = ap.parse_args()
    for n in build_site():
        print(n)
    handler = lambda *args, **kw: Handler(*args, directory=str(SITE), **kw)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", a.port), handler) as srv:
        base = f"http://127.0.0.1:{a.port}"
        print(f"\n起動しました（Ctrl+C で停止）\n  統計図          {base}/\n  天気図 標準版   {base}/maps/\n  天気図 画用紙版 {base}/maps/board/")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n停止しました")


if __name__ == "__main__":
    main()
