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

## 構成（実装済み）
```
week_forecast_charts/
  # 統計図（C1〜C3・ENS）
  fetch_ens.py / climatology.py / stats.py / charts.py / make_charts.py / pipeline.py
  # 天気図（アンサンブル平均・標準版/画用紙版）
  fetch_ens_mean.py fetch_gefs.py fetch_gsm.py   # 取得層（モデルごと。F 辞書を返す）
  mean_charts.py mean_pipeline.py maps_manifest.py   # 作図・実行・manifest（モデルを知らない）
  publish.py        # gh-pages への公開（PNG・manifest・画面だけ）
  serve_local.py    # ローカル閲覧（127.0.0.1:8803）
  check_availability.py ops/ launchd/   # 配信時刻の実測・トークン期限通知
  web/ maps_web/    # 統計図の画面 / 標準版・画用紙版の画面（Vanilla JS）
  .github/workflows/  # update, deploy-web, update-maps, maps-model
  tests/
  data/ output/ logs/   # git除外
```
層の約束: モデルに依存するのは取得層だけ。統計・作図はモデルを知らない。

## 主要な設計判断
| 項目 | 決定 | 理由 |
|---|---|---|
| 主データ | ECMWF ENS（オープンデータ）＋NOAA GEFS（決定）。GSM はローカル専用 | 無料・再配布条件が明確・メンバー数が多い。気象庁の有料配信は契約しない |
| 期間 | まず「〜7日」「8〜14日」の週平均 | 週間予報・2週間気温予報に対応 |
| 平年値 | NCEP/NCAR 再解析 日別長期平均 1991–2020（決定） | 認証不要。ERA5 は CDS アカウントが必要なため見送り |
| 地域 | 北半球・東アジア・日本の3つ | 大規模パターンと日本への影響を両方見る |
| 公開 | PNG・manifest・画面だけを GitHub Pages（gh-pages）へ（決定・公開済み） | GRIB2 は載せず容量は約0.5GB。GSM は公開しない |

## 未決事項
[PLAN.md](PLAN.md) の「未決事項」を参照。
