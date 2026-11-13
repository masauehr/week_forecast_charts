#!/usr/bin/env python
# coding: utf-8
"""ECMWF ENS（アンサンブル）オープンデータの取得層。

配信: https://data.ecmwf.int/forecasts/{YYYYMMDD}/{HH}z/ifs/0p25/enfo/{YYYYMMDDHH}0000-{step}h-enfo-ef.{grib2,index}
- 1ステップ=1ファイル（約4.4GB）。索引(.index)のバイト範囲だけ取る（必要な変数・面の50メンバー分で数十MB）。
- 摂動メンバー(type=pf, number=1..50)のみ。コントロール(cf)はこのパスに無い。em/es/ep（平均・標準偏差・確率）も配信されない。
- 1回のRange要求に約3秒の待ち時間があるため、並列で取る（順次171秒 → 並列10で23秒。実測）。
  配信側は同時接続に上限があるので並列数は抑える（既定10）。

取得層の約束: 統計以降はモデルを知らない。この層は「(メンバー, 緯度, 経度) の配列」を返す関数に閉じ込める。
nwp_chart_web の nwp_data.py の取得部分をコピーして調整したもの（共通部品化しない方針）。
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

# pygrib より前に PROJ のデータ場所を指定（conda 環境で必要になることがある）
_proj = os.path.join(sys.prefix, "share", "proj")
if os.path.isdir(_proj):
    os.environ.setdefault("PROJ_LIB", _proj)

import numpy as np
import requests

ECM_BASE = "https://data.ecmwf.int/forecasts"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WeekToSeason/0.1)"}
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data" / "ecmwf_ens"
WORKERS = 10               # 並列Range取得の既定数（配信側の同時接続上限に配慮して抑える）
MAX_STEP = 360             # ENS 00/12UTC の最大予報時間[h]

# 取り扱う変数: 名前 -> (index の param, levtype, levelist or None, pygrib の shortName, pygrib の level)
VARS = {
    "z500": ("gh", "pl", "500", "gh", 500),     # 500hPa ジオポテンシャル高度[gpm]
    "t850": ("t", "pl", "850", "t", 850),       # 850hPa 気温[K]
    "msl": ("msl", "sfc", None, "msl", 0),      # 海面更正気圧[Pa]
}


def parse_init(text: str) -> datetime:
    """YYYYMMDDHH（UTC）→ datetime"""
    return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def base_url(init: datetime, step: int) -> str:
    """索引・拡張子を除いたURL。"""
    return (f"{ECM_BASE}/{init:%Y%m%d}/{init:%H}z/ifs/0p25/enfo/"
            f"{init:%Y%m%d%H}0000-{step}h-enfo-ef")


def _head_ok(url: str) -> bool:
    try:
        r = requests.head(url, headers=HEADERS, timeout=30, allow_redirects=True)
        return r.status_code == 200
    except requests.RequestException:
        return False


def candidate_inits(days_back: int = 3):
    """新しい順の初期値候補（00/12UTC。ENSが360hまで出るのはこの2つ）。"""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    out = []
    for d in range(days_back + 1):
        day = now - timedelta(days=d)
        for hh in (12, 0):
            t = day.replace(hour=hh)
            if t <= now:
                out.append(t)
    return out


def find_latest_complete(max_step: int = MAX_STEP, days_back: int = 3):
    """最後のステップまで揃っている最新の初期値（公開途中を避ける）。無ければ None。"""
    for init in candidate_inits(days_back):
        if _head_ok(base_url(init, max_step) + ".index") and _head_ok(base_url(init, 0) + ".index"):
            return init
    return None


# ------------------------------------------------------------------ 索引 → バイト範囲
def read_index(init: datetime, step: int):
    r = requests.get(base_url(init, step) + ".index", headers=HEADERS, timeout=60)
    r.raise_for_status()
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def select_rows(rows, names):
    """索引から対象変数の行を選ぶ。(変数名, 行) のリストを offset 順で返す。"""
    want = {}
    for n in names:
        param, levtype, level, _, _ = VARS[n]
        want[(param, levtype, level)] = n
    out = []
    for x in rows:
        if x.get("type") != "pf":
            continue
        k = (x["param"], x.get("levtype"), x.get("levelist"))
        if k in want:
            out.append((want[k], x))
    out.sort(key=lambda t: t[1]["_offset"])
    return out


def merge_ranges(ranges):
    """隣り合うバイト範囲 (offset, length) を結合する。"""
    merged = []
    for off, ln in sorted(ranges):
        if merged and merged[-1][0] + merged[-1][1] == off:
            merged[-1] = (merged[-1][0], merged[-1][1] + ln)
        else:
            merged.append((off, ln))
    return merged


def _get_range(url: str, off: int, ln: int) -> bytes:
    hdr = dict(HEADERS, Range=f"bytes={off}-{off + ln - 1}")
    for attempt in range(4):
        try:
            r = requests.get(url, headers=hdr, timeout=120)
            if r.status_code in (200, 206) and len(r.content) == ln:
                return r.content
            raise requests.RequestException(f"HTTP {r.status_code} len={len(r.content)}")
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def step_path(init: datetime, step: int, name: str, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    """変数ごとのファイルの置き場所: data_dir/{初期値}/f{step:03d}_{変数}.grib2。

    変数ごとに分ける理由: 「ファイルがあれば取得済み」と判定するため。変数を後から足しても、
    既存の別変数のファイルに邪魔されずに取得できる。
    """
    return Path(data_dir) / f"{init:%Y%m%d%H}" / f"f{step:03d}_{name}.grib2"


def fetch_step(init: datetime, step: int, name: str = "z500",
               data_dir: Path = DEFAULT_DATA_DIR, workers: int = WORKERS) -> Path | None:
    """指定ステップの変数 name（全メンバー）を step_path に保存。既存ならスキップ。

    GRIB2 はメッセージを連結してそのまま読める。失敗したら None（途中ファイルは残さない）。
    """
    dest = step_path(init, step, name, data_dir)
    if dest.exists():
        return dest
    rows = select_rows(read_index(init, step), (name,))
    if not rows:
        return None
    ranges = merge_ranges([(x["_offset"], x["_length"]) for _, x in rows])
    url = base_url(init, step) + ".grib2"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    try:
        with ThreadPoolExecutor(workers) as ex:
            chunks = list(ex.map(lambda r: _get_range(url, *r), ranges))
        with open(tmp, "wb") as f:
            for c in chunks:                  # ex.map は入力順に返すので offset 順に並ぶ
                f.write(c)
        tmp.rename(dest)
        return dest
    except requests.RequestException as e:
        print(f"  ダウンロード失敗 {dest.name}: {e}")
        tmp.unlink(missing_ok=True)
        return None


def fetch_steps(init: datetime, steps, names=("z500", "t850", "msl"),
                data_dir: Path = DEFAULT_DATA_DIR, workers: int = WORKERS):
    """複数ステップ×複数変数を順に取得（1ファイル内で並列）。{(step, 変数): Path or None} を返す。"""
    out = {}
    for s in steps:
        for n in names:
            t0 = time.time()
            out[(s, n)] = fetch_step(init, s, n, data_dir, workers)
            print(f"  f{s:03d} {n}: {'OK' if out[(s, n)] else 'NG'} {time.time() - t0:.1f}秒", flush=True)
    return out


# ------------------------------------------------------------------ 読み込み（→ メンバー配列）
def load_members(path: Path, name: str):
    """GRIB2 から変数 name の全メンバーを読み、(data[member, lat, lon], lats, lons, members) を返す。

    緯度は昇順・経度は 0〜360 の昇順に正規化する（ECMWFは -180〜180 で来ることがある）。
    """
    import pygrib
    _, _, _, short, level = VARS[name]
    grbs = pygrib.open(str(path))
    try:
        sel = [g for g in grbs.select(shortName=short) if level == 0 or g.level == level]
        if not sel:
            raise ValueError(f"{name} が {path} に見つかりません")
        sel.sort(key=lambda g: g.perturbationNumber)
        lats, lons = sel[0].latlons()
        arrs = [g.values for g in sel]
        members = [int(g.perturbationNumber) for g in sel]
    finally:
        grbs.close()
    lat1 = lats[:, 0]
    lon1 = np.mod(lons[0, :], 360.0)
    data = np.ma.filled(np.stack(arrs).astype("float32"), np.nan)
    if lat1[0] > lat1[-1]:                   # 緯度を昇順に
        data = data[:, ::-1, :]
        lat1 = lat1[::-1]
    order = np.argsort(lon1)                  # 経度を 0..360 昇順に
    return data[:, :, order], lat1, lon1[order], members


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ECMWF ENS の取得（探索用CLI）")
    ap.add_argument("--init", help="YYYYMMDDHH（省略時は最新の揃った初期値）")
    ap.add_argument("--steps", type=int, nargs="+", default=[120])
    ap.add_argument("--vars", nargs="+", default=["z500", "t850", "msl"])
    a = ap.parse_args()
    init = parse_init(a.init) if a.init else find_latest_complete()
    print("初期値:", init)
    if init:
        fetch_steps(init, a.steps, tuple(a.vars))
