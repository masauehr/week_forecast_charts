# DESIGN — week_forecast_charts

## 方針
- **データ → 統計（NumPy）→ 描画（cartopy/matplotlib）→ PNG** の単純な3段構成。
- 取得は索引のバイト範囲で必要な変数・気圧面だけ部分取得（nwp_chart_web と同じ手法をコピーして使う）。
- 描画の見た目は気象庁の週間予報支援資料風（偏差は暖色/寒色の塗り、等値線は実値）を目指す。

## 処理の流れ
```
fetch   : アンサンブル全メンバーの必要変数を取得（GRIB2）
stats   : メンバー平均・スプレッド・確率を計算（期間平均化もここ）
clim    : 平年値（日別/週別）を読み込み、偏差を計算
render  : 図種ごとの描画関数で PNG を作る
publish : （任意）manifest.json を作り Web 表示
```

## 構成案（実装時）
```
week_forecast_charts/
  fetch_ens.py      # アンサンブル取得
  climatology.py    # 平年値の作成・読込
  stats.py          # 平均・スプレッド・確率・期間平均
  charts.py         # 図種定義（CHARTS）と描画関数
  regions.py        # 表示領域（北半球・東アジア・日本）
  make_charts.py    # CLI（--init 初期値 --period 期間）
  web/              # 閲覧画面（Vanilla JS）
  tests/
  data/ output/ logs/   # git除外
```

## 主要な設計判断（暫定）
| 項目 | 暫定決定 | 理由 |
|---|---|---|
| 主データ | ECMWF ENS（オープンデータ）＋NOAA GEFS | 無料・再配布条件が明確・メンバー数が多い |
| 期間 | まず「〜7日」「8〜14日」の週平均 | 週間予報・2週間気温予報に対応 |
| 平年値 | ERA5またはJRA-3Qから1991–2020気候値を自作 | 気象庁平年値(1991–2020)と期間を揃える |
| 地域 | 北半球・東アジア・日本の3つ | 大規模パターンと日本への影響を両方見る |
| 公開 | まずローカル、容量を見て後で判断 | Pages容量に余裕がないため |

## 未決事項
[PLAN.md](PLAN.md) の「未決事項」を参照。
