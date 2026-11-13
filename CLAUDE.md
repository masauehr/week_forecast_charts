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

## ドキュメント更新
変更したら [week-to-season-charts.md](week-to-season-charts.md) と `pc_docs/manuals/automation/week-to-season-charts.md` の**両方**を更新し、`pc_docs/README.md` の表も直す。
