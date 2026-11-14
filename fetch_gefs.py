#!/usr/bin/env python
# coding: utf-8
"""NOAA GEFS（GFSのアンサンブル）の「アンサンブル平均」(geavg) の取得と、天気図用の辞書 F への変換。

配信（AWS Open Data・米政府データ）:
  https://noaa-gefs-pds.s3.amazonaws.com/gefs.{YYYYMMDD}/{HH}/atmos/pgrb2ap5/geavg.t{HH}z.pgrb2a.0p50.f{FFF}  （+ .idx）
- geavg = 30メンバー+コントロールの平均。0.5°・約15MB/ステップ（全変数）。索引(.idx)のバイト範囲で必要分だけ取る。
- 予報時間: 0〜240hは3時間毎、384hまで。週間予報用に12時間毎（0〜168h）を使う。
- 気圧面の変数は 200/500/700/850/925hPa。**300hPaの気温・湿度と700hPaの上昇流は平均(geavg)に無い**
  （各メンバーの pgrb2b にだけある）。そのため 300hPa の図（jet300・t300）は GEFS では作らない。
  700hPaの上昇流は各メンバーの平均で補う（fetch_vvel700_mean）。

F の形式は nwp_chart_web の nwp_data.load_fields と同じ（mean_charts.py がそのまま使える）:
  {"lats","lons","msl"(hPa),"sp"(hPa),"u10","v10","t2"(℃),"tcc"(%),"rr"(mm/h),"rr_h"(降水の平均時間),
   "p": {気圧面: {"gh"(m),"t"(℃),"u","v","r"(%),"w"(hPa/h)}}}
nwp_data.py の GFS 部分をコピーして調整したもの（共通部品化しない方針）。
"""
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

_proj = os.path.join(sys.prefix, "share", "proj")
if os.path.isdir(_proj):
    os.environ.setdefault("PROJ_LIB", _proj)

import numpy as np
import requests

S3 = "https://noaa-gefs-pds.s3.amazonaws.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WeekToSeason/0.1)"}
WORKERS = 8
PLEVELS = (925, 850, 700, 500, 200)       # geavg に t・r・u・v・gh が揃う面（300hPaは気温・湿度が無い）
STEPS_WEEK = tuple(range(0, 169, 12))     # 週間予報用: 0〜168hを12時間毎（14+1時刻）
MAX_STEP = 168
MEMBERS = ["c00"] + [f"p{n:02d}" for n in range(1, 31)]   # 各メンバー（上昇流の平均用）


def parse_init(text: str) -> datetime:
    return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def _dir(init: datetime) -> str:
    return f"{S3}/gefs.{init:%Y%m%d}/{init:%H}/atmos"


def mean_url(init: datetime, step: int) -> str:
    return f"{_dir(init)}/pgrb2ap5/geavg.t{init:%H}z.pgrb2a.0p50.f{step:03d}"


def member_url(init: datetime, step: int, member: str) -> str:
    """各メンバー（pgrb2b。geavg が持たない 700hPa の上昇流・300hPa の気温/湿度がある）"""
    p = "gec00" if member == "c00" else f"gep{member[1:]}"
    return f"{_dir(init)}/pgrb2bp5/{p}.t{init:%H}z.pgrb2b.0p50.f{step:03d}"


def _head_ok(url: str) -> bool:
    try:
        return requests.head(url, headers=HEADERS, timeout=30, allow_redirects=True).status_code == 200
    except requests.RequestException:
        return False


def candidate_inits(days_back: int = 3):
    """新しい順の初期値候補（00/12UTC）。"""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    out = []
    for d in range(days_back + 1):
        for hh in (12, 0):
            t = (now - timedelta(days=d)).replace(hour=hh)
            if t <= now:
                out.append(t)
    return out


def find_latest_complete(max_step: int = MAX_STEP, days_back: int = 3):
    """最後のステップ(168h)まで揃っている最新の初期値。無ければ None。"""
    for init in candidate_inits(days_back):
        if _head_ok(mean_url(init, max_step) + ".idx") and _head_ok(mean_url(init, 0) + ".idx"):
            return init
    return None


# ------------------------------------------------------------------ 索引 → バイト範囲
def read_idx(url: str):
    """.idx を読み、[(番号, 開始バイト, 長さ or None, 変数, 面, 予報の説明)] を返す。"""
    r = requests.get(url + ".idx", headers=HEADERS, timeout=60)
    r.raise_for_status()
    rows = []
    for line in r.text.splitlines():
        f = line.split(":")
        if len(f) >= 6:
            rows.append([int(f[0]), int(f[1]), f[3], f[4], f[5]])
    out = []
    for i, (n, off, var, lev, fc) in enumerate(rows):
        ln = rows[i + 1][1] - off if i + 1 < len(rows) else None
        out.append((n, off, ln, var, lev, fc))
    return out


def _window(fc: str):
    """'18-24 hour acc fcst' → 6（積算・平均の窓幅[h]）。窓が無ければ None。"""
    m = re.search(r"(\d+)-(\d+) hour (?:acc|ave)", fc)
    return int(m.group(2)) - int(m.group(1)) if m else None


def select_records(idx):
    """天気図に要る記録を選ぶ。降水・雲量は窓が最短のものを採る。"""
    want = []
    for n, off, ln, var, lev, fc in idx:
        lv = None
        m = re.fullmatch(r"(\d+) mb", lev)
        if m:
            lv = int(m.group(1))
        keep = False
        if var in ("HGT", "TMP", "UGRD", "VGRD") and lv in PLEVELS:
            keep = True
        elif var == "RH" and lv in PLEVELS:
            keep = True
        elif var in ("TMP", "RH") and lev == "2 m above ground" and var == "TMP":
            keep = True
        elif var in ("UGRD", "VGRD") and lev == "10 m above ground":
            keep = True
        elif var == "PRMSL" and lev == "mean sea level":
            keep = True
        elif var == "PRES" and lev == "surface":
            keep = True
        if keep:
            want.append((n, off, ln, var, lev, fc))
    for var, lev in (("APCP", "surface"), ("TCDC", "entire atmosphere")):
        cand = [x for x in idx if x[3] == var and x[4] == lev and _window(x[5])]
        if cand:
            want.append(min(cand, key=lambda x: _window(x[5])))
    return sorted(want, key=lambda x: x[1])


def _range_get(url: str, off: int, ln: int | None) -> bytes:
    hdr = dict(HEADERS, Range=f"bytes={off}-{'' if ln is None else off + ln - 1}")
    for attempt in range(4):
        try:
            r = requests.get(url, headers=hdr, timeout=120)
            if r.status_code in (200, 206):
                return r.content
            raise requests.RequestException(f"HTTP {r.status_code}")
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_mean(init: datetime, step: int, dest: Path, workers: int = WORKERS) -> Path:
    """geavg の必要な記録だけを dest に保存（GRIB2は連結してそのまま読める）。"""
    url = mean_url(init, step)
    recs = select_records(read_idx(url))
    if not recs:
        raise RuntimeError(f"索引から必要な記録を選べません: {url}")
    with ThreadPoolExecutor(workers) as ex:
        chunks = list(ex.map(lambda r: _range_get(url, r[1], r[2]), recs))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(b"".join(chunks))
    tmp.rename(dest)
    return dest


def fetch_vvel700_mean(init: datetime, step: int, workers: int = WORKERS):
    """31メンバー(pgrb2b)から 700hPa の鉛直p速度(VVEL・Pa/s)だけを範囲取得して平均する。(lat, lon) を返す。"""
    import pygrib

    def one(member):
        url = member_url(init, step, member)
        rec = [x for x in read_idx(url) if x[3] == "VVEL" and x[4] == "700 mb"]
        if not rec:
            return None
        data = _range_get(url, rec[0][1], rec[0][2])
        with tempfile.NamedTemporaryFile(suffix=".grib2") as f:
            f.write(data)
            f.flush()
            g = pygrib.open(f.name)
            v = g[1].values
            g.close()
        return np.ma.filled(v, np.nan).astype("float32")

    with ThreadPoolExecutor(workers) as ex:
        arrs = [a for a in ex.map(one, MEMBERS) if a is not None]
    if not arrs:
        return None
    return np.mean(np.stack(arrs), axis=0)


# ------------------------------------------------------------------ 読み込み → F
def load_F(path: Path, vvel700=None):
    """fetch_mean で保存したGRIB2を F 辞書にする。vvel700: 700hPaの平均VVEL(Pa/s)（任意）。"""
    import pygrib
    grbs = pygrib.open(str(path))
    d = {"p": {}}
    lats = lons = None
    rr_h = None
    try:
        for g in grbs:
            short, lev = g.shortName, g.level
            tol = g.typeOfLevel
            v = np.ma.filled(g.values, np.nan).astype("float32")
            if lats is None:
                lats, lons = g.latlons()
            if tol == "isobaricInhPa":
                d["p"].setdefault(int(lev), {})[short] = v
            elif short in ("prmsl", "msl"):
                d["msl"] = v
            elif short == "sp":
                d["sp"] = v
            elif short in ("10u", "u") and tol == "heightAboveGround" and lev == 10:
                d["u10"] = v
            elif short in ("10v", "v") and tol == "heightAboveGround" and lev == 10:
                d["v10"] = v
            elif short in ("2t", "t") and tol == "heightAboveGround" and lev == 2:
                d["t2"] = v
            elif short == "tcc":
                d["tcc"] = v
            elif short == "tp":
                d["tp"] = v
                rr_h = int(g.endStep - g.startStep) if hasattr(g, "startStep") else None
    finally:
        grbs.close()
    F = {"lats": lats[:, 0], "lons": np.mod(lons[0, :], 360.0), "rr": None, "rr_h": rr_h or 6}
    F["msl"] = d["msl"] / 100.0
    F["sp"] = d["sp"] / 100.0
    F["u10"], F["v10"] = d["u10"], d["v10"]
    F["t2"] = d["t2"] - 273.15
    F["tcc"] = d.get("tcc", np.zeros_like(F["msl"]))
    if "tp" in d and rr_h:
        F["rr"] = (d["tp"] / rr_h).clip(min=0)
    F["p"] = {}
    for lv, z in d["p"].items():
        if not all(k in z for k in ("gh", "t", "u", "v")):
            continue
        F["p"][lv] = {"gh": z["gh"], "t": z["t"] - 273.15, "u": z["u"], "v": z["v"],
                      "r": z.get("r", np.full_like(z["t"], 50.0)),
                      "w": np.zeros_like(z["t"])}
    if vvel700 is not None and 700 in F["p"]:
        F["p"][700]["w"] = vvel700 * 36.0                  # Pa/s → hPa/h（nwp_chart_web と同じ換算）
    if F["lats"][0] > F["lats"][-1]:                       # 緯度を昇順（南→北）へ
        F["lats"] = F["lats"][::-1]
        for k in ("msl", "sp", "u10", "v10", "t2", "tcc", "rr"):
            if F.get(k) is not None:
                F[k] = F[k][::-1, :]
        for z in F["p"].values():
            for k in z:
                z[k] = z[k][::-1, :]
    order = np.argsort(F["lons"])                          # 経度を 0..360 昇順へ
    if not np.all(order == np.arange(len(order))):
        F["lons"] = F["lons"][order]
        for k in ("msl", "sp", "u10", "v10", "t2", "tcc", "rr"):
            if F.get(k) is not None:
                F[k] = F[k][:, order]
        for z in F["p"].values():
            for k in z:
                z[k] = z[k][:, order]
    return F
