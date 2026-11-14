#!/usr/bin/env python
# coding: utf-8
"""アンサンブル平均の天気図（標準版・画用紙版用）を作るパイプライン。

1ステップ（予報時間）ごとに別プロセスで「取得 → F 辞書 → 全図種×全地域を描画」を行い、GRIB2 は一時ディレクトリに置いて
すぐ削除する（ディスクに残さない）。出力: {out}/{model}/{初期値YYYYMMDDHH}/{地域}/{図種}_{FFF}.png ＋ {out}/manifest.json（maps_manifest.py）

例: python mean_pipeline.py --model gefs --init 2026111312 --out output/maps
    python mean_pipeline.py --model gefs --steps 0 12 24 --jobs 2     （一部だけ）
"""
import argparse
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

# 描画のスレッド競合を避ける（mean_charts を import する前に）
for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_k, "1")

import fetch_gefs as fg

MODEL_LABEL = {"gefs": "GEFS mean", "ens": "ECMWF ENS mean"}
ROOT = Path(__file__).resolve().parent


def out_name(chart, region, ft):
    """{地域}/{図種}_{FFF}.png（nwp_chart_web の画像規則と同じ。画面をほぼそのまま使うため）"""
    return f"{region}/{chart}_{ft:03d}.png"


def _step_worker(args):
    """1ステップ分（失敗したら最大3回やり直す。配信側の接続リセット等の一時的なエラー対策）。"""
    import requests
    for attempt in range(3):
        try:
            return _step_once(args)
        except (requests.RequestException, ConnectionError, OSError) as e:
            print(f"  f{args[2]:03d}: 失敗（{type(e).__name__}）。{attempt + 1}/3回目", flush=True)
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))


def _step_once(args):
    """1ステップ分: 取得 → F → 全図種×全地域を描画。作ったファイル名の一覧を返す。"""
    model, init_text, step, out_dir, regions = args
    import mean_charts as mc
    init = fg.parse_init(init_text)
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="wsc_mean_") as td:
        if model == "gefs":
            p = fg.fetch_mean(init, step, Path(td) / f"f{step:03d}.grib2")
            F = fg.load_F(p, extras=fg.fetch_extras(init, step))      # 700hPa上昇流・300hPa気温と湿度をメンバー平均で補う
        elif model == "ens":
            import fetch_ens as fe
            import fetch_ens_mean as em
            F = em.build_F(fe.parse_init(init_text), step)
        else:
            raise SystemExit(f"未対応のモデル: {model}")
    made = []
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for chart in mc.charts_for(F):
        for region in mc.regions_of(chart):
            if regions and region not in regions:
                continue
            f = out_dir / out_name(chart, region, step)
            f.parent.mkdir(parents=True, exist_ok=True)
            mc.render_chart(chart, region, F, init, step, str(f), model=MODEL_LABEL[model])
            made.append(out_name(chart, region, step))
    print(f"  f{step:03d}: {len(made)}枚 {time.time() - t0:.0f}秒", flush=True)
    return made


def run(model, init, out_root, steps=None, regions=None, jobs=4):
    import mean_charts as mc
    mc.warm_up()                      # 海岸線データのダウンロード・読み込みを並列処理の前に済ませる
    init_text = f"{init:%Y%m%d%H}"
    out_dir = Path(out_root) / model / init_text
    steps = list(steps) if steps else list(fg.STEPS_WEEK)
    tasks = [(model, init_text, s, str(out_dir), regions) for s in steps]
    allf = []
    if jobs <= 1:
        for t in tasks:
            allf += _step_worker(t)
    else:
        with ProcessPoolExecutor(jobs) as ex:
            for made in ex.map(_step_worker, tasks):
                allf += made
    return out_dir, allf


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["gefs", "ens"], default="gefs")
    ap.add_argument("--init", help="YYYYMMDDHH（UTC）。省略時は最新の揃った初期値")
    ap.add_argument("--out", default=str(ROOT / "output" / "maps"))
    ap.add_argument("--steps", type=int, nargs="+")
    ap.add_argument("--regions", nargs="+")
    ap.add_argument("--jobs", type=int, default=None, help="同時に処理するステップ数（既定: gefs=4, ens=2）")
    ap.add_argument("--skip-if-published", action="store_true",
                    help="その初期値がすでに公開サイトにあれば何も作らず終了（cron-job.org の多めの起動用）")
    a = ap.parse_args()
    if a.jobs is None:
        a.jobs = 4 if a.model == "gefs" else 2
    if a.init:
        init = fg.parse_init(a.init)
    elif a.model == "ens":
        import fetch_ens as fe
        init = fe.find_latest_complete(max_step=max(fg.STEPS_WEEK))
    else:
        init = fg.find_latest_complete()
    if init is None:
        raise SystemExit("揃った初期値が見つかりません")
    print("初期値:", init, flush=True)
    if a.skip_if_published:
        import publish
        if f"{init:%Y%m%d%H}" in publish.published_map_inits(a.model):
            print("すでに公開済みのため何もしません")
            raise SystemExit(0)
    t0 = time.time()
    import maps_manifest
    try:
        d, files = run(a.model, init, a.out, a.steps, a.regions, a.jobs)
    finally:
        maps_manifest.write_manifest(a.out)         # 途中で止まっても、できた分は manifest に載せる（画面が「読めません」にならない）
    print(f"完了: {len(files)}枚 {time.time() - t0:.0f}秒 → {d}")
