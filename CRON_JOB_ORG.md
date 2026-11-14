# cron-job.org 設定ガイド — 図の定期更新（week_forecast_charts）

作成: 2026-11-14 ／ 方式は nwp_chart_web の [CRON_JOB_ORG.md](../nwp_chart_web/CRON_JOB_ORG.md) と同じ（コピーして調整。共通部品化しない）

## 0. 概要
```
cron-job.org（決めた時刻に）
  → POST https://api.github.com/repos/masauehr/week_forecast_charts/actions/workflows/update.yml/dispatches
       （専用トークンで認証。本文 {"ref":"main"}）
  → GitHub Actions の update が起動
       最新の揃った初期値を探す → 揃っていない／すでに公開済みなら何もせず終了（冪等）
       揃っていれば 取得→作図→gh-pages へ公開（約8分）
  → https://masauehr.github.io/week_forecast_charts/ が更新される
```
- cron-job.org は「時刻になったら合図を送る」だけ。作図は GitHub Actions が行う。Mac には依存しない。
- **何度呼んでも安全**: 初期値の指定が空の起動は `pipeline.py --skip-if-published` で、揃っていない回・公開済みの回は数十秒で終わる。だから起動を多めに設定できる。
- GitHub の `schedule` は予備にも使わない（遅れ・間引きがあり、今回は cron-job.org に一本化）。

## 1. 起動時刻（暫定）
ENS（00Z/12Z）の360時間分が揃うのは初期値から約8〜11時間後と想定（nwp_chart_web の ECMWF の実測 約7〜11時間から推定。**ENS の実測は未了**）。実測は `check_availability.py`（2節）で記録し、数日分たまったら `python check_availability.py --report` で時刻を見直す。

| 狙い | UTC（各時の :30） | cron-job.org に入力する時（JST＝UTC+9） |
|---|---|---|
| 00Z 初期値 | 8, 9, 10, 11 時 | **17, 18, 19, 20 時** |
| 12Z 初期値 | 20, 21, 22, 23 時 | **5, 6, 7, 8 時** |

- 分は :30。1日8回（空振りは安い）。**cron-job.org の画面は JST で入力する**（UTCと取り違えると別の時刻になる。nwp_chart_web で起きた）。
- 実測で早く揃うと分かれば、遅い時刻を減らし早い時刻を足す。

## 2. 配信時刻の実測（launchd）
```
mkdir -p ~/projects/week_forecast_charts/logs
cp ~/projects/week_forecast_charts/launchd/com.masahiro.week_forecast_charts_availability.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.masahiro.week_forecast_charts_availability.plist
```
10分おきに配信状況を確認（HEAD要求のみ）して `logs/availability.csv` に記録する。集計は `python check_availability.py --report`（met_env_310）。止めるときは `launchctl bootout gui/$(id -u)/com.masahiro.week_forecast_charts_availability`。Mac がスリープの間は確認できず、遅れが大きく出る（csv の検出間隔が大きい行は精度が低い）。

## 3. 専用トークンの作成・更新（ユーザーが行う）
### 3-1. トークンの作成（GitHub の画面）
1. GitHub → 右上アイコン → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
2. Token name: `week_to_season_charts`（現在のトークンの名前。新規に作り直すなら `week_forecast_charts` など分かりやすい名でよい。期限は 2027-02-12）
3. Expiration: **90 days**（最大でも期限付き）
4. Repository access: **Only select repositories** → `masauehr/week_forecast_charts` だけ
5. Permissions → Repository permissions → **Actions: Read and write**（それ以外は付けない。Metadata: Read-only は自動）
6. Generate token → 表示された値を**このとき1回だけ**コピー（チャット・ファイル・リポジトリには書かない）。期限の日時も控える

### 3-2. 期限の通知（Slack DM）を設定する
```
mkdir -p ~/.config/week_forecast_charts
echo "2027-02-12T00:00:00Z" > ~/.config/week_forecast_charts/token_expiry     # 3-1 で控えた期限（UTC）に書き換える
cp ~/.config/nwp_chart_web/slack_to ~/.config/week_forecast_charts/slack_to    # nwp_chart_web と同じ通知先
cp ~/projects/week_forecast_charts/launchd/com.masahiro.week_forecast_charts_token_notify.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.masahiro.week_forecast_charts_token_notify.plist
/opt/homebrew/bin/python3 ~/projects/week_forecast_charts/ops/token_expiry_notify.py --test    # テスト通知（届けば正常）
```
期限の14・7・3・2・1日前に通知し、期限切れ後は毎日通知する（毎日9:10 JST）。**トークンを更新したら `token_expiry` を新しい期限に書き換える**（忘れると期限切れ通知が毎日届く）。

### 3-3. トークンの更新
GitHub の Fine-grained tokens で `week_to_season_charts`（トークン名）を Regenerate（または新規作成）→ cron-job.org の各ジョブのヘッダー `Authorization: Bearer <新しい値>` を差し替え → `~/.config/week_forecast_charts/token_expiry` を書き換え。

## 4. cron-job.org のジョブ設定
1. https://cron-job.org でアカウント作成（無料）→ ログイン → **CREATE CRONJOB**
2. Title: `week_forecast_charts update`
3. URL: `https://api.github.com/repos/masauehr/week_forecast_charts/actions/workflows/update.yml/dispatches`
4. Execution schedule: **User-defined**。分=30、時=1節の表の JST の時（17,18,19,20,5,6,7,8）、日・月・曜日=すべて。Time zone は Asia/Tokyo
5. Advanced → Request method: **POST**、Request body: `{"ref":"main"}`
6. Advanced → Headers（4つ）:
   - `Authorization` : `Bearer <3-1のトークン>`
   - `Accept` : `application/vnd.github+json`
   - `X-GitHub-Api-Version` : `2022-11-28`
   - `Content-Type` : `application/json`
7. NOTIFICATIONS タブ: 「execution of the cronjob fails」を ON（Notify after **1** failure）、「the cronjob will be disabled because of too many failures」を ON（自動停止の通知は必須）。「succeeds after it failed before」と「TLS certificate is about to expire」は OFF でよい（宛先は GitHub のAPIで管理できないため）。Notify via は既定の all notification channels（登録はアカウントのメール。足りなければ Settings の Notification channels で確認）。なお cron-job.org が検知する失敗は HTTP が 2xx 以外のとき（401 トークン不正・期限切れ、403 権限不足、404 URL違い）だけ。Actions の中での作図の失敗は検知できないので、GitHub の Actions 失敗メールで気づく。
8. 保存後、**Test run** で `204 No Content` が返ることを確認（401＝トークン不正・期限切れ、403＝権限不足、404＝URL違い）
9. テスト実行で GitHub の Actions タブに `update` が起動すれば成功（揃い済み・公開済みなら数十秒で何もせず終了する）

## 5. 確認・トラブル
- 動作確認: GitHub の Actions → `update` の履歴。公開済みの回は「すでに公開済みのため何もしません」、新しい初期値の回は約8分で公開まで進む。
- 公開されない: 初期値が揃っていない（`check_availability.py --report`）／トークン期限切れ（401）／cron-job.org のジョブが失敗続きで自動無効化されていないか。
- 手動で作る: GitHub の Actions → update → Run workflow（初期値を指定すれば公開済みでも作り直す）。

## 6. 天気図用ジョブ（update-maps・暫定・2026-11-14）
アンサンブル平均の天気図（標準版・画用紙版）を更新するジョブ。統計図（4節）とは**別のジョブ**を作る。

### 6-1. 起動時刻（暫定）
- GEFS は 168h が初期値から**約5.0時間後**に揃う（実測1件: 2026-11-14 00Z で 5.03h）。ENS は天気図に必要な 168h まで（360hではない）。ENS の実測は未了で、統計図と同じく約8〜11時間後と想定する。
- 1回の起動で GEFS と ENS の両方を流す（`model` を省略＝`all`）。揃っていないモデルは何もせず終了し、次の起動で拾う（冪等）。
- 統計図と重ならないよう**分は :45**にする（公開だけは `concurrency: publish` で順番待ちになるので、重なっても取りこぼしはしない）。

| 狙い | UTC（各時の :45） | cron-job.org に入力する時（JST） |
|---|---|---|
| 00Z 初期値 | 8, 9, 10, 11 時 | **17, 18, 19, 20 時** |
| 12Z 初期値 | 20, 21, 22, 23 時 | **5, 6, 7, 8 時** |

実測がたまったら `python check_availability.py --report` で見直す（早く揃うなら遅い時刻を減らす）。

### 6-2. 設定（4節との違いだけ）
1. Title: `week_forecast_charts update-maps`
2. URL: `https://api.github.com/repos/masauehr/week_forecast_charts/actions/workflows/update-maps.yml/dispatches`
3. Execution schedule: User-defined。分=45、時=上表の JST の時（17,18,19,20,5,6,7,8）。Time zone は Asia/Tokyo
4. Request method: POST、Request body: `{"ref":"main"}`、ヘッダー4つと通知は4節と同じ（**同じトークンを使える**）
5. Test run で `204 No Content` を確認 → GitHub の Actions に `update-maps` が起動すれば成功

### 6-3. 所要時間と確認
- GEFS は build 約5分＋publish 約1分、ENS は build 約30分＋publish 約1分。公開はモデルごとに独立（早い GEFS が先に出る）。
- GSM はローカル専用なので、このジョブには含まれない（`update-maps.yml` は ens/gefs のみ）。
- 確認: 公開マニフェスト https://masauehr.github.io/week_forecast_charts/maps/output/manifest.json にモデルごとの初期値が出る（gsm が出ていないこと）。
