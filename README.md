# week_forecast_charts（週間〜2週間予報用 天気図）

詳しくは [week-forecast-charts.md](week-forecast-charts.md) を参照。

## 目的
週間天気予報（〜7日）・2週間気温予報（〜15日先）の**判断に使う天気図**を作る。
**1か月以上の長期予報は別プロジェクト [long_range_charts](../long_range_charts/) に移した**（2026-11-14。旧名 week_to_season_charts から名称変更。GitHub のリポジトリ名・公開サイトの URL も新名に変更済み）。
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
| [CRON_JOB_ORG.md](CRON_JOB_ORG.md) | cron-job.org での定期起動の設定手順（4節は画面に沿った手順・Enable job の確認）・トークン・期限通知 |
| [PLAN.md](PLAN.md) | フェーズ計画・未決事項・進捗 |
| [week-forecast-charts.md](week-forecast-charts.md) | マニュアル（pc_docs/manuals/automation/ と同内容） |

## 公開サイト
https://masauehr.github.io/week_forecast_charts/ （初期値・図種・期間・領域を切り替えて閲覧。PNGとmanifestだけを公開。GRIB2は載せない）

## 天気図（標準版・画用紙版）

- ローカルでは、設定ファイル `region_config.json` で「沖縄周辺」を九州・関東などに入れ替えられる（手順・書式・9地域の設定例は [week-forecast-charts.md](week-forecast-charts.md) の「ローカル地域「沖縄周辺」の入れ替え方法」）。
https://masauehr.github.io/week_forecast_charts/maps/ （標準版）／ https://masauehr.github.io/week_forecast_charts/maps/board/ （画用紙版）
ECMWF ENS 平均・GEFS 平均の**アンサンブル平均場から作った天気図**（地上・850hPa×2・700hPa・500hPa・300/200hPaなど）を、0〜168時間（12時間毎）で閲覧。気象庁 GSM（決定論）の図はローカル専用で、公開しない（`python serve_local.py` で手元だけで比較できる）。

## ローカルで見る・手元のデータを最新にする（2026-11-23）
- 起動: `python serve_local.py`（met_env_310。http://127.0.0.1:8803/ ・/maps/ ・/maps/board/）。
- **公開分の同期**: GRIB2 は公開側にも無いので、ENS を手元で作ると2時間強かかる。代わりに公開サイトの統計図・ENS/GEFS天気図のPNGを `sync_public.py` で取り込む（画面の「同期」ボタン／launchd 30分おき `launchd/com.masahiro.week_forecast_charts_sync.plist`）。GSM は対象外。
- **GSM（ローカル専用）の自動更新**: `update_gsm.py`（launchd 1時間おき `launchd/com.masahiro.week_forecast_charts_gsm.plist`。3日より古いものは自動削除）。
- 画面を直した直後に古い表示が残るときはハードリロード（Cmd+Shift+R）。サーバーは html/js/css に `no-cache` を付けている。
- launchd の登録手順は各 plist 冒頭のコメント。詳しくは [week-forecast-charts.md](week-forecast-charts.md)。

## 状況
2026-11-14 新規作成。**統計図（C1・C2・C3）と天気図（ENS・GEFS の標準版・画用紙版）を GitHub Actions で作図し、GitHub Pages で公開済み。cron-job.org が1日8回ずつ起動（統計図 :30・天気図 :45。**統計図のジョブは 2026-11-23 まで無効（Enable OFF）で11/14から止まっていたが、同日有効化済み**）。** GSM（決定論）はローカル専用で実装済み。残りは ENS の配信時刻の実測にもとづく起動時刻の見直し。
