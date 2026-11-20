# CLAUDE.md — week_forecast_charts

## 概要
週間予報・2週間気温予報（〜15日先）の判断に使う天気図（アンサンブル統計・平年偏差・確率・アンサンブル平均の天気図）を作る。
**1か月以上の長期予報はこのプロジェクトでは扱わない**（2026-11-14 に `../long_range_charts` へ移した）。旧名は week_to_season_charts。**GitHub のリポジトリ名・公開サイトURLは 2026-11-14 に week_forecast_charts へ変更済み**（旧URLは404）。**トークン名 `week_to_season_charts` は旧名のまま**（トークンは名前ではなくリポジトリに紐づくので有効）。cron-job.org のジョブURLは新名に直す（CRON_JOB_ORG.md の4・6節）。
マニュアルは [week-forecast-charts.md](week-forecast-charts.md)、設計は [DESIGN.md](DESIGN.md)、図種は [CHARTS.md](CHARTS.md)、データ源は [DATA_SOURCES.md](DATA_SOURCES.md)、計画は [PLAN.md](PLAN.md)。

## 実行環境
- Python: `/opt/anaconda3/envs/met_env_310/bin/python`（pygrib・cartopy・metpy・scipy・pytest）。`python3` は別環境になるので使わない（brew更新でpython3が切り替わる事例あり）。
- 標準では Python 4スペース、JS/HTML/CSS 2スペース。コメント・UIは日本語。

## 守ること
- **nwp_chart_web・tenkizu_web とは共通部品化しない**（必要ならコピーして調整。各リポジトリは単独クローンで動く自己完結を優先）。
- **平年値は出典と期間を必ず図に明記**する（例: 気象庁平年値 1991–2020、ERA5気候値 1991–2020）。偏差の基準が曖昧な図は出さない。
- **確率・偏差の図には、メンバー数・初期値・対象期間を図の下端に表示**する。
- **断定表現を避ける**。アンサンブル統計は「傾向」であり、予報そのものではない。
- 配信元の利用条件（ECMWF CC BY 4.0 等）に従い、出典・加工した旨を図と画面に表示する。気象庁の公式予報（週間予報・1か月予報の確率等）と混同される表示にしない。
- 気象庁の公式予報値を使う場合は `mcp__jma__*` ツールまたは公式JSONを使い、出典リンクを付ける。
- `data/`（GRIB2等）・`output/`・`logs/` は git 除外。
- 公開（GitHub Pages等）する場合は容量（Pages 1GB目安）を先に見積もる。
- push は毎回ユーザー確認が必要。

## 公開の仕組み（gh-pages ブランチ方式・2026-11-14）
- 公開先は https://masauehr.github.io/week_forecast_charts/ 。**PNG・manifest.json・画面(web/)だけ**を載せる。GRIB2・平年値は載せない（`publish.py`）。
- 図の更新は `.github/workflows/update.yml`（手動実行。初期値を指定可）→ `pipeline.py`（取得→期間平均に足し込む→GRIB2即削除→作図）→ `publish.py --src output/<初期値>`。約8分。
- 画面(web/)だけ直したら push すれば `deploy-web.yml` が数十秒で反映（`publish.py --web-only`。図は作り直さない）。
- 公開は履歴を溜めない単一の孤立コミットを force push する。update と deploy-web は同じ `concurrency: publish` を共有（競合させない）。公開ブランチを直接編集しない。
- 公開する初期値は直近8個（`publish.KEEP_DEFAULT`。1初期値約7MB）。manifest の形を変えたら `web/app.js` も直す。
- CIの日本語フォントは Noto Sans CJK JP（`charts.py` のフォント指定とワークフローの apt を揃える）。平年値は軽量版 `data/clim/clim_compact.npz` を Actions キャッシュ（`climatology.py --prepare`）。
- 図のファイル名: `ecmwf-ens_{初期値}_{c1|c2|c3high|c3low}_{p期間|f時間}_{asia|nh}.png`（`publish.parse_name` が読む）。
- **気象庁（JMBSC）の有料配信は使わない**（2026-11-14 ユーザー決定）。気象庁モデルの追加を提案しない。
- 定期起動は cron-job.org（[CRON_JOB_ORG.md](CRON_JOB_ORG.md)）。`update.yml` は初期値が空だと「揃っていない／公開済みなら何もしない」。専用トークン `week_to_season_charts` の期限は `~/.config/week_forecast_charts/token_expiry` に書き、更新したら書き換える。トークンの値は書かない・貼らない。
- C3 の確率（±1℃）は温暖化の傾向と平年値の系統差で高温側に偏る。階級確率と混同させない表現を保つ。

## アンサンブル平均の天気図（標準版・画用紙版・2026-11-14）
- 目的: 週間予報期間（0〜168h・12時間毎）の**アンサンブル平均の天気図**。モデルは ENS（ECMWF ENS 50メンバー平均・`fetch_ens_mean.py`）と GEFS（NOAA の geavg=平均ファイル・`fetch_gefs.py`）。GSM（気象庁・決定論・京大RISH配信）は**ローカル専用**（`fetch_gsm.py`。0〜168h・12時間毎・降水は12時間差）。
- 作図は nwp_chart_web の `nwp_charts.py` を `mean_charts.py` にコピーして調整したもの（共通部品化しない）。入力は `F` 辞書（msl/sp/u10/v10/t2/tcc/rr/p[気圧面][gh,t,u,v,r,w]）。**図種ごとの必要な気圧面（CHARTS の levels）が F に無ければ作らない**（`charts_for`）。GEFS の平均(geavg)には300hPaの気温・湿度と700hPaの上昇流が無いので、**各メンバー(pgrb2b・31)から範囲取得して平均して補う**（`fetch_gefs.fetch_extras`。1ステップ約24秒）。週間用のジェットは300hPaが主（jet300。jet200・t300は日本周辺・東アジア）。
- **850・925hPa の気温の等値線**: 850hPa は3℃毎・925hPa は2℃毎、ラベルは大きめ（fs=12）。日本周辺・沖縄周辺は `label_zones=("east_china_sea",)`（`LABEL_ZONES`）で、東シナ海を通る線に必ずラベルを付ける（nwp_chart_web のコピー。別々に直す）。
- **850hPa は2種に分ける**: `t850`（気温・湿数・風）と `ept850`（相当温位・風）。SSI は描かない。**湿数・EPT はアンサンブル平均場（気温・湿度）から計算**（メンバーごとに計算して平均したものではない）。マニフェストの免責にも明記してある。**平均図は前線・降水・風がなだらかになる（予報そのものではない）旨の表示を外さない**。
- 画面は nwp_chart_web の `web/` を `maps_web/` にコピーして調整（更新・同期・過去分・断面図は hidden）。画像規則・manifest は nwp_chart_web と同じ（`output/{model}/{init}/{region}/{chart}_{ft:03d}.png`、`maps_manifest.py`）。公開サイトの `maps/` 配下に置く。**localStorage のキーは `wsc_size`・`wscBoard.v2`・`wscBoard.presets.v1`**（同じドメイン masauehr.github.io の nwp_chart_web とキーを共有しない）。
- ローカルで見る: `python serve_local.py`（http://127.0.0.1:8803/ ・/maps/ ・/maps/board/。手元の output/ をそのまま表示。事前に `mean_pipeline.py`・`pipeline.py` で作る）。
- 作図: `python mean_pipeline.py --model gefs|ens [--init YYYYMMDDHH]`（1ステップ=1プロセスで 取得→F→全図種×全地域を描画。GRIB2は一時領域に置いて削除）。GEFS は全15時刻で約3分・約60MB。ENS は1ステップ約518秒（手元）／Actions では約1/4の見込み。
- 公開: Actions `update-maps`。**モデルごとに「作図→公開」が独立して流れる**（再利用ワークフロー `maps-model.yml` を ens・gefs で別々に呼ぶ。早い GEFS（約5分）は遅い ENS（約30分）を待たずに公開される。公開ジョブだけ `concurrency: publish` で順番待ち＝同時pushの取りこぼしなし）。`publish.py --maps-src output/maps/<model>/<init>`（複数可）。天気図は**モデルごとに直近3初期値**を残す（`MAPS_KEEP`。1初期値約60MB）。統計図(`charts/`)と天気図(`maps/output/`)は互いに carry する（片方の更新でもう片方を消さない）。
- 画面だけ直したら `maps_web/**` を push → `deploy-web` が反映（図は作り直さない）。

- **地域の入れ替え**: `region_config.json`（環境変数 `WFC_REGION_CONFIG`・git除外）で `okinawa` の中身を別の地域に入れ替えられる（`mean_charts.apply_region_config`。nwp_chart_web のコピー。**地域は増やさない・地域ボタンも増やさない**）。公開サイトは設定ファイルが無いので沖縄周辺のまま。直すときは nwp_chart_web と別々に。

## GSM（ローカル専用・決定論）
- **GSM の図・データは公開しない**。`maps_manifest.LOCAL_ONLY`（`MODELS["gsm"]` の `local_only`）が基準。4重に除外している（**外さない**）: ①`maps_manifest.write_manifest(public_only=True)` が載せない ②`publish.py` が `LOCAL_ONLY` のモデルの `--maps-src` を拒否 ③`mean_pipeline.py` が `GITHUB_ACTIONS=true` では GSM を作らない ④`update-maps.yml` のモデル選択は ens/gefs のみ。新しいローカル専用モデルを足すなら `local_only` を付ける。
- 作る: `python mean_pipeline.py --model gsm`（1ステップ約30秒・全15時刻で約8分・約0.9GBを取得して一時領域で削除。出力 `output/maps/gsm/<初期値>/`）。見る: `python serve_local.py`（標準版・画用紙版のモデル選択に「JMA GSM（決定論）」が出る。2モデル比較・モデル違いで ENS平均/GEFS平均と比べられる）。
- 気象庁データなので、**配信元（RISH・気象庁）の利用条件に従う**。再配布・公開する場合は条件を先に確認する（このプロジェクトでは公開しない）。

## ドキュメント更新
変更したら [week-forecast-charts.md](week-forecast-charts.md) と `pc_docs/manuals/automation/week-forecast-charts.md` の**両方**を更新し、`pc_docs/README.md` の表も直す。
