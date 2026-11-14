#!/usr/bin/env python
# coding: utf-8
"""アンサンブル平均の天気図（標準版・画用紙版）の manifest.json を作る。

nwp_chart_web の write_manifest と同じ形式（画面 maps_web/app.js・board.js をほぼそのまま使うため）。
出力配置: {out}/{model}/{初期値}/{地域}/{図種}_{FFF}.png 、一覧は {out}/manifest.json
モデル: ens=ECMWF ENS 平均（50メンバー）／gefs=GEFS 平均（NOAA）。GSM（ローカル専用・決定論）は後で追加する。
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import mean_charts as mc

CC_BY_URL = "https://creativecommons.org/licenses/by/4.0/"
ECMWF_TERMS_URL = "https://apps.ecmwf.int/datasets/licences/general/"
GEFS_REGISTRY_URL = "https://registry.opendata.aws/noaa-gefs/"

MODELS = {
    "ens": dict(label="ECMWF ENS平均"),
    "gefs": dict(label="GEFS平均"),
}
DISCLAIMER = ("本サイトの図は、元データ（アンサンブル予報）の各メンバーを平均して加工し、本アプリが作図したもので、"
              "各提供元（ECMWF・NOAA/NCEP）の公式な図ではありません。平均を取るため、前線・低気圧・降水・風の強さは"
              "実際の1つの予報よりなだらかになり、先の時刻ほど弱まります（予報そのものではなく、メンバーの平均です）。"
              "湿数・相当温位は、平均した気温・湿度から計算しています。"
              "防災・安全に関わる判断には、気象庁など公的機関の公式情報を使ってください。"
              "図の内容や利用による損害について、本サイトの作成者は責任を負いません。")


def legal_text(model: str, year: int, accessed: str) -> dict:
    """出典・ライセンス・免責・改変の表示文言（配信元の利用条件に沿った内容）。規約は変わり得るので定期的に再確認する。"""
    if model == "ens":
        short = (f"© {year} ECMWF (www.ecmwf.int). This service is based on data and products of the European Centre "
                 "for Medium-Range Weather Forecasts (ECMWF), IFS ensemble (ENS) open data, licensed under CC BY 4.0. "
                 "Modified: the 50 perturbed members were averaged and processed into charts. "
                 "ECMWF does not accept any liability for any error or omission in the data.")
        notice = [
            f"Copyright © {year} European Centre for Medium-Range Weather Forecasts (ECMWF). Source: www.ecmwf.int.",
            "Licence: Creative Commons Attribution 4.0 International (CC BY 4.0), " + CC_BY_URL
            + " （ECMWF Terms of Use: " + ECMWF_TERMS_URL + "）",
            "This service is based on data and products of the European Centre for Medium-Range Weather Forecasts (ECMWF) "
            "(IFS Medium-range Ensemble open data, 0.25°, 50 perturbed members).",
            "Modification: the original data were modified — only selected variables were used, the ensemble members were "
            "averaged, and derived quantities were computed from the mean fields into the charts shown here. "
            "These charts are not ECMWF products.",
            "Disclaimer: ECMWF does not accept any liability whatsoever for any error or omission in the data, their "
            "availability, or for any loss or damage arising from their use. The data are provided on an \"as is\" basis.",
        ]
        return dict(short=short, notice=notice, license_url=CC_BY_URL)
    short = (f"NOAA/NCEP Global Ensemble Forecast System (GEFS) ensemble mean, accessed {accessed} from "
             "registry.opendata.aws/noaa-gefs. Modified: the data were processed into charts and are not original NOAA data. "
             "Not endorsed by or affiliated with NOAA/NWS. Provided as is; use at your own risk.")
    notice = [
        f"NOAA/NCEP Global Ensemble Forecast System (GEFS) ensemble mean (0.5°) was accessed on {accessed} from {GEFS_REGISTRY_URL}",
        "Modification: the original data were modified — only selected variables were used and derived quantities were "
        "computed from the ensemble-mean fields into the charts shown here (700hPa vertical velocity is the mean of the "
        "31 members). These charts are not original, unaltered NOAA data and are not official government materials.",
        "This site is not endorsed by, and is not affiliated with, NOAA or the National Weather Service. "
        "NOAA/NWS names and logos are not used.",
        "Disclaimer: the information is provided \"as is\" without warranty of any kind; the user assumes the entire risk "
        "of its use.",
    ]
    return dict(short=short, notice=notice, license_url=GEFS_REGISTRY_URL)


def scan(out_dir: Path, model: str):
    """{out}/{model}/ を走査して、新しい初期値から [{init, regions:{地域:{図種:[ft...]}}}] を返す。"""
    inits = []
    md = Path(out_dir) / model
    if not md.is_dir():
        return inits
    for d in sorted(md.iterdir(), reverse=True):
        if not (d.is_dir() and re.fullmatch(r"\d{10}", d.name)):
            continue
        regions = {}
        for rd in sorted(d.iterdir()):
            if not rd.is_dir() or rd.name not in mc.REGIONS:
                continue
            charts = {}
            for f in rd.glob("*_*.png"):
                m = re.fullmatch(r"(\w+?)_(\d{3})\.png", f.name)
                if m and m.group(1) in mc.CHARTS:
                    charts.setdefault(m.group(1), []).append(int(m.group(2)))
            if charts:
                regions[rd.name] = {c: sorted(charts[c]) for c in mc.CHARTS if c in charts}   # 図種は高層→地上
        if regions:
            inits.append({"init": d.name, "regions": regions})
    return inits


def write_manifest(out_dir, now=None):
    out_dir = Path(out_dir)
    now = now or datetime.now(timezone.utc)
    models = {}
    for model, info in MODELS.items():
        inits = scan(out_dir, model)
        if inits:
            legal = legal_text(model, now.year, now.strftime("%Y-%m-%d"))
            models[model] = {"label": info["label"], "credit": legal["short"], "notice": legal["notice"],
                             "license_url": legal["license_url"], "inits": inits}
    manifest = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclaimer": DISCLAIMER,
        "charts": {k: v["label"] for k, v in mc.CHARTS.items()},
        "regions": {k: v["label"] for k, v in mc.REGIONS.items()},
        "models": models,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = write_manifest(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "output" / "maps")
    print("manifest.json 更新: " + (", ".join(f"{k} {len(v['inits'])}件" for k, v in m["models"].items()) or "画像なし"))
