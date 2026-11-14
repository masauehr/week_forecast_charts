# CLAUDE.md — week_to_season_charts

## 概要
週間予報・2週間気温予報・1か月/3か月予報の判断に使う天気図（アンサンブル統計・平年偏差・確率）を作る。
マニュアルは [week-to-season-charts.md](week-to-season-charts.md)、設計は [DESIGN.md](DESIGN.md)、図種は [CHARTS.md](CHARTS.md)、データ源は [DATA_SOURCES.md](DATA_SOURCES.md)、計画は [PLAN.md](PLAN.md)。

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
- 公開先は https://masauehr.github.io/week_to_season_charts/ 。**PNG・manifest.json・画面(web/)だけ**を載せる。GRIB2・平年値は載せない（`publish.py`）。
- 図の更新は `.github/workflows/update.yml`（手動実行。初期値を指定可）→ `pipeline.py`（取得→期間平均に足し込む→GRIB2即削除→作図）→ `publish.py --src output/<初期値>`。約8分。
- 画面(web/)だけ直したら push すれば `deploy-web.yml` が数十秒で反映（`publish.py --web-only`。図は作り直さない）。
- 公開は履歴を溜めない単一の孤立コミットを force push する。update と deploy-web は同じ `concurrency: publish` を共有（競合させない）。公開ブランチを直接編集しない。
- 公開する初期値は直近8個（`publish.KEEP_DEFAULT`。1初期値約7MB）。manifest の形を変えたら `web/app.js` も直す。
- CIの日本語フォントは Noto Sans CJK JP（`charts.py` のフォント指定とワークフローの apt を揃える）。平年値は軽量版 `data/clim/clim_compact.npz` を Actions キャッシュ（`climatology.py --prepare`）。
- 図のファイル名: `ecmwf-ens_{初期値}_{c1|c2|c3high|c3low}_{p期間|f時間}_{asia|nh}.png`（`publish.parse_name` が読む）。
- **気象庁（JMBSC）の有料配信は使わない**（2026-11-14 ユーザー決定）。気象庁モデルの追加を提案しない。
- 定期起動は cron-job.org（[CRON_JOB_ORG.md](CRON_JOB_ORG.md)）。`update.yml` は初期値が空だと「揃っていない／公開済みなら何もしない」。専用トークン `week-to-season-charts-dispatch` の期限は `~/.config/week_to_season_charts/token_expiry` に書き、更新したら書き換える。トークンの値は書かない・貼らない。
- C3 の確率（±1℃）は温暖化の傾向と平年値の系統差で高温側に偏る。階級確率と混同させない表現を保つ。

## ドキュメント更新
変更したら [week-to-season-charts.md](week-to-season-charts.md) と `pc_docs/manuals/automation/week-to-season-charts.md` の**両方**を更新し、`pc_docs/README.md` の表も直す。
