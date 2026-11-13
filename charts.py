#!/usr/bin/env python
# coding: utf-8
"""図種の描画（モデルに依存しない層）。

C1: 500hPa高度のアンサンブル平均（等値線）と平年偏差（塗り）。期間平均。
cartopy 0.26 の contourf(transform=PC) は帯が地図全面に広がる不具合があるため、
座標を自前で投影してから描く（nwp_chart_web と同じ対処。transform を付けない）。
"""
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.colors import BoundaryNorm, ListedColormap

# 日本語フォント（mac: Hiragino Sans）。無ければ既定フォント（日本語は豆腐になる）
plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

PC = ccrs.PlateCarree()

# 表示領域。extent は (lon0, lon1, lat0, lat1)。
REGIONS = {
    "asia": dict(label="東アジア", proj=lambda: ccrs.LambertConformal(
        central_longitude=125, central_latitude=40, standard_parallels=(25, 55)),
        extent=(95, 175, 8, 62), crop=(60, 200, -5, 80)),
    "nh": dict(label="北半球", proj=lambda: ccrs.NorthPolarStereo(central_longitude=120),
               extent=None, crop=(0, 360, 15, 90)),
}

# 偏差の塗り（gpm）。0付近の ±30 は白、青=平年より低い、赤=平年より高い
Z_ANOM_LEVELS = [-240, -180, -150, -120, -90, -60, -30, 30, 60, 90, 120, 150, 180, 240]
_BLUES = ["#08306b", "#08519c", "#2166ac", "#4393c3", "#6baed6", "#9ecae1", "#d1e5f0"]
_REDS = ["#fddbc7", "#fcbba1", "#f4a582", "#d6604d", "#b2182b", "#8c0d1f", "#67001f"]
Z_ANOM_COLORS = _BLUES + ["#ffffff"] + _REDS      # 区間数 = レベル数(14)+1 = 15 → 7 + 1 + 7


def _crop(field, lats, lons, crop):
    lon0, lon1, lat0, lat1 = crop
    ji = np.where((lats >= lat0) & (lats <= lat1))[0]
    ii = np.where((lons >= lon0) & (lons <= lon1))[0]
    return field[np.ix_(ji, ii)], lats[ji], lons[ii]


def _map(region):
    r = REGIONS[region]
    fig = plt.figure(figsize=(10, 7.6), dpi=110)
    ax = fig.add_axes([0.03, 0.17, 0.94, 0.73], projection=r["proj"]())
    if r["extent"]:
        ax.set_extent(r["extent"], crs=PC)
    else:
        ax.set_extent((-180, 180, 20, 90), crs=PC)
    ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#f4f1e8", zorder=0)
    ax.coastlines(resolution="110m", linewidth=0.6, color="#555555", zorder=6)
    gl = ax.gridlines(draw_labels=False, linewidth=0.3, color="#999999", alpha=0.6,
                      xlocs=range(-180, 181, 30), ylocs=range(-80, 81, 10))
    gl.set_zorder(5)
    return fig, ax, r


def _xy(ax, lats, lons):
    """格子の座標を地図の投影座標へ自前で変換する。"""
    lon2, lat2 = np.meshgrid(lons, lats)
    p = ax.projection.transform_points(PC, lon2, lat2)
    return p[..., 0], p[..., 1]


def render_c1(zmean, zanom, lats, lons, *, region, init, period_label, steps, members,
              clim_text, source_text, out_path):
    """C1 を描いて PNG に保存する。

    zmean: アンサンブル平均の期間平均 Z500 (lat, lon) [gpm]
    zanom: 平年偏差 (lat, lon) [gpm]
    """
    fig, ax, r = _map(region)
    anom, la, lo = _crop(zanom, lats, lons, r["crop"])
    zm, _, _ = _crop(zmean, lats, lons, r["crop"])
    X, Y = _xy(ax, la, lo)
    cmap = ListedColormap(Z_ANOM_COLORS)
    norm = BoundaryNorm([-1e4] + Z_ANOM_LEVELS + [1e4], cmap.N)
    cf = ax.contourf(X, Y, anom, levels=[-1e4] + Z_ANOM_LEVELS + [1e4], cmap=cmap, norm=norm,
                     extend="neither", zorder=1)
    cs = ax.contour(X, Y, zm, levels=np.arange(4800, 6001, 60), colors="#222222", linewidths=0.8, zorder=3)
    ax.contour(X, Y, zm, levels=[5400, 5880], colors="#000000", linewidths=1.8, zorder=4)
    ax.clabel(cs, levels=np.arange(4800, 6001, 120), fmt="%d", fontsize=7, inline=True)

    cax = fig.add_axes([0.20, 0.125, 0.60, 0.017])
    cb = fig.colorbar(cf, cax=cax, orientation="horizontal", ticks=Z_ANOM_LEVELS)
    cb.ax.tick_params(labelsize=7)
    cb.set_label("平年偏差 (gpm)  青=平年より低い / 赤=平年より高い", fontsize=8)

    fig.text(0.03, 0.945, "500hPa高度  アンサンブル平均と平年偏差", fontsize=15, weight="bold")
    fig.text(0.03, 0.915, f"{period_label}の平均  [{r['label']}]  等値線: アンサンブル平均(60gpm毎・太線=5400/5880)",
             fontsize=9.5, color="#333333")
    vt0, vt1 = steps[0], steps[-1]
    foot = (f"ECMWF IFS ENS ({members}メンバー) 初期値 {init:%Y-%m-%d %H}UTC  対象: 予報{vt0}〜{vt1}時間 "
            f"({len(steps)}時刻の平均)   平年値: {clim_text}\n"
            f"{source_text}   アンサンブル統計に基づく傾向であり、気象庁の公式予報ではありません。")
    fig.text(0.03, 0.012, foot, fontsize=6.8, color="#444444", va="bottom", linespacing=1.5)
    fig.savefig(out_path, facecolor="white")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------- C2 スパゲッティ図
# 等値線(gpm)と色。5400=寒気・トラフの目安、5700=中緯度の流れの目安（調整可）
SPAGHETTI_LEVELS = ((5400, "#1f6fb4"), (5700, "#d9541e"))


def render_c2(members_z, zmean, lats, lons, *, region, init, step, members, source_text, out_path,
              levels=SPAGHETTI_LEVELS):
    """C2: 500hPa高度の等値線を全メンバー重ねて描く（スパゲッティ図）。1時刻の予報。

    members_z: (member, lat, lon) [gpm]、zmean: アンサンブル平均 (lat, lon)。
    線が束ねられていれば確実性が高く、ばらけていれば低い。
    """
    fig, ax, r = _map(region)
    _, la, lo = _crop(zmean, lats, lons, r["crop"])
    sl_j, sl_i = slice(None, None, 2), slice(None, None, 2)      # 0.5°に間引いて軽くする
    la2, lo2 = la[sl_j], lo[sl_i]
    X, Y = _xy(ax, la2, lo2)
    for lev, color in levels:
        for m in range(members_z.shape[0]):
            f, _, _ = _crop(members_z[m], lats, lons, r["crop"])
            ax.contour(X, Y, f[sl_j, sl_i], levels=[lev], colors=color, linewidths=0.6, alpha=0.45, zorder=2)
        zm, _, _ = _crop(zmean, lats, lons, r["crop"])
        ax.contour(X, Y, zm[sl_j, sl_i], levels=[lev], colors="#000000", linewidths=2.2, zorder=4)

    fig.text(0.03, 0.945, "500hPa高度  スパゲッティ図", fontsize=15, weight="bold")
    vt = init.replace(tzinfo=None)
    from datetime import timedelta
    valid = vt + timedelta(hours=step)
    legend = "  ".join(f"{lev}gpm" for lev, _ in levels)
    fig.text(0.03, 0.915, f"予報{step}時間後（有効 {valid:%m/%d %H}UTC） [{r['label']}]  等値線: {legend}  "
             "細線=各メンバー・太黒線=アンサンブル平均", fontsize=9.5, color="#333333")
    # 凡例（色）
    for k, (lev, color) in enumerate(levels):
        fig.text(0.12 + 0.14 * k, 0.125, f"━ {lev}gpm", color=color, fontsize=10, weight="bold")
    foot = (f"ECMWF IFS ENS ({members}メンバー) 初期値 {init:%Y-%m-%d %H}UTC。線が束ねられている領域は予報の確実性が高く、"
            "ばらける領域は低い。\n"
            f"{source_text}   アンサンブル統計に基づく傾向であり、気象庁の公式予報ではありません。")
    fig.text(0.03, 0.012, foot, fontsize=6.8, color="#444444", va="bottom", linespacing=1.5)
    fig.savefig(out_path, facecolor="white")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------- C3 850hPa気温 偏差と確率
T_ANOM_LEVELS = [-8, -6, -4, -3, -2, -1, 1, 2, 3, 4, 6, 8]            # K（=℃の差）
T_ANOM_COLORS = ["#08306b", "#2166ac", "#4393c3", "#92c5de", "#c6dbef", "#e6eff7", "#ffffff",
                 "#fde5d6", "#fcc7ab", "#f4a582", "#d6604d", "#b2182b", "#67001f"]
PROB_LEVELS = [10, 20, 30, 40, 50, 60, 70, 80, 90]                      # %
PROB_CMAP_HIGH = "YlOrRd"
PROB_CMAP_LOW = "PuBu"


def _axes(fig, rect, region):
    """指定位置に地図の軸を作る（共通の海岸線・格子）。"""
    r = REGIONS[region]
    ax = fig.add_axes(rect, projection=r["proj"]())
    ax.set_extent(r["extent"] if r["extent"] else (-180, 180, 20, 90), crs=PC)
    ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#f4f1e8", zorder=0)
    ax.coastlines(resolution="110m", linewidth=0.5, color="#555555", zorder=6)
    gl = ax.gridlines(draw_labels=False, linewidth=0.3, color="#999999", alpha=0.6,
                      xlocs=range(-180, 181, 30), ylocs=range(-80, 81, 10))
    gl.set_zorder(5)
    return ax, r


def render_c3(tanom_mean, prob, lats, lons, *, region, init, period_label, steps, members, kind,
              threshold, clim_text, source_text, out_path, below_ground=None):
    """C3: 左=T850 平年偏差のアンサンブル平均(K)、右=平年偏差が閾値を超える(下回る)メンバーの割合(%)。

    kind: "high"=偏差が +threshold 以上、"low"=偏差が −threshold 以下 の確率。
    tanom_mean, prob: (lat, lon)。prob は 0..1。
    """
    if below_ground is not None:                  # 850hPaが地面より下の格子は外挿値なので描かない
        tanom_mean = np.where(below_ground, np.nan, tanom_mean)
        prob = np.where(below_ground, np.nan, prob)
    fig = plt.figure(figsize=(14, 6.8), dpi=100)
    axl, r = _axes(fig, [0.02, 0.19, 0.465, 0.69], region)
    axr, _ = _axes(fig, [0.515, 0.19, 0.465, 0.69], region)

    a, la, lo = _crop(tanom_mean, lats, lons, r["crop"])
    p, _, _ = _crop(prob * 100.0, lats, lons, r["crop"])
    Xl, Yl = _xy(axl, la, lo)
    Xr, Yr = _xy(axr, la, lo)

    cm1 = ListedColormap(T_ANOM_COLORS)
    b1 = [-1e3] + T_ANOM_LEVELS + [1e3]
    cf1 = axl.contourf(Xl, Yl, a, levels=b1, cmap=cm1, norm=BoundaryNorm(b1, cm1.N), zorder=1)
    cmap2 = plt.get_cmap(PROB_CMAP_HIGH if kind == "high" else PROB_CMAP_LOW)
    colors2 = ["#ffffff"] + [cmap2(v) for v in np.linspace(0.12, 0.95, len(PROB_LEVELS))]
    cm2 = ListedColormap(colors2)
    b2 = [0] + PROB_LEVELS + [100.0001]
    cf2 = axr.contourf(Xr, Yr, p, levels=b2, cmap=cm2, norm=BoundaryNorm(b2, cm2.N), zorder=1)
    axr.contour(Xr, Yr, p, levels=[50], colors="#222222", linewidths=1.0, zorder=3)

    cal = fig.add_axes([0.10, 0.125, 0.30, 0.016])
    cb1 = fig.colorbar(cf1, cax=cal, orientation="horizontal", ticks=T_ANOM_LEVELS)
    cb1.ax.tick_params(labelsize=7)
    cb1.set_label("850hPa気温の平年偏差 (℃)  青=低い / 赤=高い", fontsize=8)
    car = fig.add_axes([0.60, 0.125, 0.30, 0.016])
    cb2 = fig.colorbar(cf2, cax=car, orientation="horizontal", ticks=PROB_LEVELS)
    cb2.ax.tick_params(labelsize=7)
    word = f"+{threshold:g}℃以上" if kind == "high" else f"−{threshold:g}℃以下"
    cb2.set_label(f"平年偏差が{word}となるメンバーの割合 (%)  黒線=50%", fontsize=8)

    fig.text(0.02, 0.945, "850hPa気温  平年偏差と確率", fontsize=15, weight="bold")
    fig.text(0.02, 0.912, f"{period_label}の平均  [{r['label']}]  左: アンサンブル平均の偏差  右: 偏差{word}の確率", fontsize=9.5,
             color="#333333")
    foot = (f"ECMWF IFS ENS ({members}メンバー) 初期値 {init:%Y-%m-%d %H}UTC  対象: 予報{steps[0]}〜{steps[-1]}時間 "
            f"({len(steps)}時刻の平均)   平年値: {clim_text}\n"
            f"確率は「メンバーの期間平均偏差が閾値を超えた割合」で、気象庁の高い/平年並/低いの階級確率とは定義が異なります。"
            f"{source_text}   アンサンブル統計に基づく傾向であり、気象庁の公式予報ではありません。")
    fig.text(0.02, 0.012, foot, fontsize=6.8, color="#444444", va="bottom", linespacing=1.5)
    fig.savefig(out_path, facecolor="white")
    plt.close(fig)
    return out_path
