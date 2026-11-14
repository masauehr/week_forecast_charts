#!/usr/bin/env python
# coding: utf-8
"""気象庁 全球モデル(GSM・決定論)の取得（京都大学 RISH）と、天気図用の辞書 F への変換。**ローカル専用モデル**。

nwp_chart_web の gsm_source.py をコピーして、週間予報用（0〜168時間・12時間毎・降水は12時間差）に調整したもの
（共通部品化しない方針）。GSM の図は**公開しない**（maps_manifest.LOCAL_ONLY・publish.py・Actions で除外）。
気象庁の配信データ(GSM)は決定論の1メンバーで、アンサンブル平均の図（ENS・GEFS）との比較用。

データ提供元: 京都大学生存圏研究所 (RISH) 気象庁データアーカイブ
  http://database.rish.kyoto-u.ac.jp/arch/jmadata/data/gpv/original/{YYYY}/{MM}/{DD}/
  Z__C_RJTD_{YYYYMMDDHH}0000_GSM_GPV_Rgl_FD{DDHH}_grib2.bin（全球0.5°・1ファイル=1予報時間・約33MB）
  FD は DDHH 表記（例 24h→0100・36h→0112）。00/12UTC初期値は 0〜84h が6時間毎、〜264h が12時間毎。
降水(APCP)は初期時刻からの積算なので、12時間前のファイルとの差を 12 で割って mm/h にする（rr_h=12）。
F の形式は nwp_chart_web の load_fields と同じ（mean_charts.py がそのまま使える）。GRIB2 は一時領域に置いて使い終わったら削除する。
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_proj = os.path.join(sys.prefix, "share", "proj")
if os.path.isdir(_proj):
    os.environ.setdefault("PROJ_LIB", _proj)

import numpy as np
import requests

BASE_URL = "http://database.rish.kyoto-u.ac.jp/arch/jmadata/data/gpv/original"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WeekForecast/0.1)"}
STEPS_WEEK = tuple(range(0, 169, 12))       # 週間予報用: 0〜168hを12時間毎
STEP_H = 12                                 # 降水の差分に使う間隔
MAX_STEP = 168


def ft_to_ddhh(ft: int) -> int:
    """予報時間[h] → FD の DDHH 数値（例 18h→18, 24h→100, 36h→112）"""
    return (ft // 24) * 100 + (ft % 24)


def ddhh_to_ft(ddhh: int) -> int:
    return (ddhh // 100) * 24 + (ddhh % 100)


def gsm_filename(init: datetime, ft: int) -> str:
    return f"Z__C_RJTD_{init:%Y%m%d%H}0000_GSM_GPV_Rgl_FD{ft_to_ddhh(ft):04d}_grib2.bin"


def parse_init(text: str) -> datetime:
    return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def _get_text(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        return r.text if r.status_code == 200 else None
    except requests.RequestException as e:
        print(f"  RISHへの接続に失敗: {e}")
        return None


def list_remote(day: datetime) -> dict:
    """指定日(UTC)のRISHディレクトリを調べ、{初期時刻(YYYYMMDDHH): [FT,...]}（Rglのみ）を返す。"""
    text = _get_text(f"{BASE_URL}/{day:%Y/%m/%d}/")
    if text is None:
        return {}
    found = {}
    for init, ddhh in set(re.findall(r"Z__C_RJTD_(\d{10})0000_GSM_GPV_Rgl_FD(\d{4})_grib2\.bin", text)):
        found.setdefault(init, []).append(ddhh_to_ft(int(ddhh)))
    return {k: sorted(v) for k, v in found.items()}


def find_latest_complete(max_step: int = MAX_STEP, steps=STEPS_WEEK, days_back: int = 3, hours=(0, 12)):
    """steps（12時間毎）が max_step まで全部RISHに揃っている最新の初期値（00/12UTC）。無ければ None。"""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    need = set(s for s in steps if s <= max_step)
    for d in range(days_back + 1):
        found = list_remote(today - timedelta(days=d))
        for init_s in sorted(found, reverse=True):
            init = parse_init(init_s)
            if hours and init.hour not in hours:
                continue
            if need <= set(found[init_s]):
                return init
    return None


def download(init: datetime, ft: int, dest_dir: Path) -> Path | None:
    """Rgl 1ファイルを dest_dir へ取得（失敗したら None。壊れたファイルは残さない）。"""
    fn = gsm_filename(init, ft)
    dest = Path(dest_dir) / fn
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    url = f"{BASE_URL}/{init:%Y/%m/%d}/{fn}"
    for attempt in range(3):
        try:
            with requests.get(url, headers=HEADERS, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        f.write(chunk)
            tmp.rename(dest)
            return dest
        except requests.RequestException as e:
            tmp.unlink(missing_ok=True)
            if attempt == 2:
                print(f"  ダウンロード失敗 {fn}: {e}")
                return None
    return None


# ------------------------------------------------------------------ 読み込み
SURFACE = {
    "msl": ("prmsl", "meanSea", 0),
    "sp": ("sp", "surface", 0),
    "u10": ("10u", "heightAboveGround", 10),
    "v10": ("10v", "heightAboveGround", 10),
    "t2": ("2t", "heightAboveGround", 2),
}
PLEVELS = (925, 850, 700, 500, 300, 200)    # 週間用の図に使う気圧面（Rglに975は無い）
PVARS = ("gh", "t", "u", "v", "r", "w")


def _scan(path: Path):
    """GRIB2を1回走査して生の場を集める（Rglは1ファイル1時間）。"""
    import pygrib
    want = {v: ("s", k) for k, v in SURFACE.items()}
    for lv in PLEVELS:
        for k in PVARS:
            want[(k, "isobaricInhPa", lv)] = ("p", (lv, k))
    out = {"p": {}, "tp": None, "tcc": None}
    lats = lons = None
    grbs = pygrib.open(str(path))
    try:
        for m in grbs:
            if m.typeOfLevel == "surface" and m.shortName == "unknown" \
                    and m.parameterCategory == 1 and m.parameterNumber == 8:
                # 積算降水量 APCP（初期時刻からの積算 mm）。pygribの表に無く name が unknown になる
                if int(m.startStep) == 0:
                    out["tp"] = np.asarray(m.values, dtype=np.float32)
                continue
            key = (m.shortName, m.typeOfLevel, m.level)
            if key in want:
                kind, k = want[key]
                vals = np.asarray(m.values, dtype=np.float32)
                if lats is None:
                    la, lo = m.latlons()
                    lats, lons = la[:, 0], lo[0, :]
                if kind == "s":
                    out[k] = vals
                else:
                    out["p"].setdefault(k[0], {})[k[1]] = vals
            elif (m.typeOfLevel == "surface" and m.shortName == "unknown"
                  and m.parameterCategory == 6 and m.parameterNumber == 1):
                out["tcc"] = np.asarray(m.values, dtype=np.float32)      # 全雲量 %
    finally:
        grbs.close()
    out["lats"], out["lons"] = lats, lons
    return out


def load_F(path: Path, prev_path: Path | None = None):
    """Rgl（全球0.5°）1ファイルを F 辞書にする。prev_path は12時間前のファイル（あれば12時間平均の降水 rr[mm/h] を作る）。
    FT=12 のときは前の積算が0なので、そのまま 12 で割る（prev_path は不要）。"""
    cur = _scan(path)
    rr = None
    if cur["tp"] is not None:
        prev = 0.0
        if prev_path is not None and Path(prev_path).exists():
            pv = _scan(prev_path)
            prev = pv["tp"] if pv["tp"] is not None else 0.0
        rr = ((cur["tp"] - prev) / STEP_H).clip(min=0)
    F = {"p": {}, "rr": rr, "rr_h": STEP_H}
    for k in ("msl", "sp", "u10", "v10", "t2", "tcc", "lats", "lons"):
        F[k] = cur.get(k)
    F["p"] = {lv: dict(d) for lv, d in cur["p"].items() if all(k in d for k in ("gh", "t", "u", "v"))}
    F["msl"] = F["msl"] / 100.0                 # Pa → hPa
    F["sp"] = F["sp"] / 100.0                   # 地表気圧 Pa → hPa（地面下のマスクに使う）
    F["t2"] = F["t2"] - 273.15                  # K → ℃
    if F["tcc"] is None:
        F["tcc"] = np.zeros_like(F["msl"])
    for d in F["p"].values():
        d["t"] = d["t"] - 273.15
        d["w"] = d["w"] * 36.0 if "w" in d else np.zeros_like(d["t"])      # Pa/s → hPa/h（上昇が負）
        if "r" not in d:
            d["r"] = np.full_like(d["t"], 50.0)
    if F["lats"][0] > F["lats"][-1]:            # 緯度を昇順（南→北）へ
        F["lats"] = F["lats"][::-1]
        for k in ("msl", "sp", "u10", "v10", "t2", "tcc", "rr"):
            if F.get(k) is not None:
                F[k] = F[k][::-1, :]
        for d in F["p"].values():
            for k in d:
                d[k] = d[k][::-1, :]
    return F


def build_F(init: datetime, step: int, tmp_dir: Path):
    """初期値 init・予報時間 step[h] の GSM を取得して F にする（ファイルは tmp_dir に置く。呼び出し側で削除）。"""
    p = download(init, step, tmp_dir)
    if p is None:
        raise RuntimeError(f"GSM f{step:03d} の取得に失敗しました")
    prev = None
    if step > STEP_H:
        prev = download(init, step - STEP_H, tmp_dir)
        if prev is None:
            raise RuntimeError(f"GSM f{step - STEP_H:03d}（降水の差分用）の取得に失敗しました")
    return load_F(p, prev)
