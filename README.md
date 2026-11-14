# week_forecast_charts（週間〜2週間予報用 天気図）

詳しくは [week-forecast-charts.md](week-forecast-charts.md) を参照。

## 目的
週間天気予報（〜7日）・2週間気温予報（〜15日先）の**判断に使う天気図**を作る。
**1か月以上の長期予報は別プロジェクト [long_range_charts](../long_range_charts/) に移した**（2026-11-14。旧名 week_to_season_charts から名称変更。GitHub のリポジトリ名・公開サイトの URL は旧名 `week_to_season_charts` のまま）。
通常の「ある1時刻の予報図」（nwp_chart_web）ではなく、**アンサンブル予報の統計（平均・ばらつき・確率）と平年からの偏差**を主役にした図を扱う。

## 通常の天気図との違い
| 項目 | nwp_chart_web（短期〜中期） | week_forecast_charts（週間〜2週間） |
|---|---|---|
| 主役 | 決定論予報（1メンバー） | アンサンブル平均・スプレッド・確率 |
| 時間軸 | 初期値からの時刻（FT） | 期間平均（週平均・5日平均・2週間平均） |
| 値 | 実値 | **平年偏差**・階級（高い/平年並/低い）確率 |
| 見方 | 前線・低気圧の位置 | 大気の大規模パターン（偏西風の蛇行・ブロッキング・極渦） |

## 作る図の候補（詳細は [CHARTS.md](CHARTS.md)）
1. 500hPa高度のアンサンブル平均・平年偏差（週平均）
2. 500hPa高度のスパゲッティ図（特定等値線の全メンバー重ね描き）
3. 850hPa気温の平年偏差・平年より高い/低い確率
4. 海面気圧のアンサンブル平均とスプレッド
5. 降水量の期間積算・平年比・確率
6. 地点別プルーム（気温・降水の時系列＋箱ひげ）

## ドキュメント一覧
| ファイル | 内容 |
|---|---|
| [README.md](README.md) | 概要（このファイル） |
| [CLAUDE.md](CLAUDE.md) | Claude Code 向け作業ルール・守ること |
| [DESIGN.md](DESIGN.md) | 設計方針・構成・処理の流れ |
| [CHARTS.md](CHARTS.md) | 図種カタログ（各図の目的・使う要素・読み方） |
| [DATA_SOURCES.md](DATA_SOURCES.md) | データ源・利用条件・平年値の扱い |
| [CRON_JOB_ORG.md](CRON_JOB_ORG.md) | cron-job.org での定期起動の設定手順・トークン・期限通知 |
| [PLAN.md](PLAN.md) | フェーズ計画・未決事項・進捗 |
| [week-forecast-charts.md](week-forecast-charts.md) | マニュアル（pc_docs/manuals/automation/ と同内容） |

## 公開サイト
https://masauehr.github.io/week_forecast_charts/ （初期値・図種・期間・領域を切り替えて閲覧。PNGとmanifestだけを公開。GRIB2は載せない）

## 天気図（標準版・画用紙版）
https://masauehr.github.io/week_forecast_charts/maps/ （標準版）／ https://masauehr.github.io/week_forecast_charts/maps/board/ （画用紙版）
ECMWF ENS 平均・GEFS 平均の**アンサンブル平均場から作った天気図**（地上・850hPa×2・700hPa・500hPa・200hPaなど）を、0〜168時間（12時間毎）で閲覧。

## 状況
2026-11-14 新規作成。**ECMWF ENS で C1（500hPa高度の平均と偏差）・C2（スパゲッティ）・C3（850hPa気温の偏差と確率）を実装し、GitHub Actions（手動実行）で作図、GitHub Pages で公開済み。** 次は cron-job.org での自動化。
