#!/usr/bin/env python
# coding: utf-8
"""アンサンブルの統計（モデルに依存しない層）。

入力は常に「(メンバー, 緯度, 経度) の配列」。取得層(fetch_ens など)がモデル差を吸収し、
この層以降はモデル名を知らない（気象庁モデルへ横展開できるようにするための約束）。
"""
import numpy as np


def period_mean(fields):
    """複数ステップの配列 [(member, lat, lon), ...] を時間平均して (member, lat, lon) にする。

    メンバーごとに期間平均してから、アンサンブル統計を取る（期間平均の予報としての不確実性を見るため）。
    """
    return np.mean(np.stack(fields, axis=0), axis=0)


def ens_mean(x):
    """アンサンブル平均 (lat, lon)。"""
    return np.mean(x, axis=0)


def ens_spread(x):
    """アンサンブルスプレッド＝メンバー間の標準偏差 (lat, lon)。ddof=1（標本標準偏差）。"""
    return np.std(x, axis=0, ddof=1)


def prob_above(x, threshold):
    """メンバーのうち threshold を超えた割合[0..1] (lat, lon)。threshold はスカラーか (lat, lon)。"""
    return np.mean(x > threshold, axis=0)


def prob_below(x, threshold):
    return np.mean(x < threshold, axis=0)


def anomaly(x, clim):
    """偏差 = x − 平年値。x は (lat, lon) か (member, lat, lon)、clim は (lat, lon)。"""
    return x - clim
