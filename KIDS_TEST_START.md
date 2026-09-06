# 最初の1シーンを Acer + C922n で試す

対象は `finger_colorfull_dots_acer.py` → `finger_colorfull_dots_2.py`。候補ブランチは `codex/rebirth2026-production-candidate`。現段階は人間の実地確認前であり、安定版ではない。

## 起動

1. AcerにC922n USBカメラを接続する。Windowsの検出名は `c922 Pro Stream Webcam`。別のシーンやTouchDesignerがカメラを使っている場合は、その作業を保存して通常終了する。
2. 既存シーンを動かしているPython環境を指定する。依存関係を勝手に更新しない。
3. このリポジトリの `Start Kids Test.cmd` を実行する。既定はリポジトリ内 `.venv`、なければPATHの `python`。`KIDZDISCO_PYTHON` の指定が最優先。

PowerShellで既存の映像用環境を指定する例。このAcerでpreflightと短時間の候補起動を確認したPython 3.12.10を使用する。環境変数の指定と起動は同じPowerShellで行う。

```powershell
Set-Location -LiteralPath 'C:\Users\go\Documents\ChatGPT\New project'
$env:KIDZDISCO_PYTHON = 'C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe'
& '.\Start Kids Test.cmd' --check
& '.\Start Kids Test.cmd'
```

`--check` は依存ライブラリとMediaPipe Hands APIを確認し、カメラやウィンドウを開かない。結果は `test_reports/kids_preflight_*.json`。起動成功を意味する検査ではない。

通常起動時は試験IDごとのログ/メトリクスを `test_reports/kids_trial_*/` に保存する。30分で止めるには `& '.\Start Kids Test.cmd' --duration-minutes 30`。20回切替と12時間試験の準備は [ENDURANCE_TEST_PLAN.md](ENDURANCE_TEST_PLAN.md) を参照。12時間試験はまだ開始していない。

通常起動ではAcer内の操作UIも有効になる。起動ログの `[Operator]` 行のURLを `#token=` 以降も含めてブラウザで開く。露出・ズームを映像へ適用し、確認できた値をJSON保存できる。MacBookから操作するためのPAN指定と確認手順は [OPERATOR_PANEL.md](OPERATOR_PANEL.md) を参照。MacBookからの実通信は未確認。

Managerを直接起動する場合も、同じ映像用Pythonを指定する。UIを有効にするには `--operator-port` が必要。

```powershell
& $env:KIDZDISCO_PYTHON manager.py --config configs/kids_test_acer.json --operator-port 8766
```

1シーンだけを起動し、先読み・ジェスチャー切替・遷移演出を無効にしている。UIの「次のシーンへ」も、この設定では同じシーンを起動し直す。映像はAcerのプライマリ画面。Managerが物理カメラを1つだけ所有し、子シーンはその共有メモリへ接続する。C922名を特定できなければ停止する。

候補プロファイルは1280×720、MJPG、30fps要求、露出-5。初回フレーム取得後に露出が-4へ戻る事象を確認し、指定値の補正後は基準シーンで30秒・約30fps・途中終了なし・正常終了を確認した。詳細は [C922_EXPOSURE_DRIFT_20260906.md](C922_EXPOSURE_DRIFT_20260906.md) を参照。回帰は84件通過しているが、長時間安定性や見え方の合格ではない。

ユーザーの最新方針により、部屋の暗さを含むFPSの追加調査は後回しにする。露出は会場の照明と動きの見え方を見ながらMacのUIで調整し、採用値を保存する。上の-5や30fps要求を現場の合格値と固定しない。

## 子供が遊ぶ前の確認

1. 起動ログに `READY`、`START`、`START_ACK`、正の `frame_id` を持つ `FIRST_FRAME` が順に出る。
2. 映像がC922の実映像であることを確認。画面の中央、左上、右上、左下、右下で指先に白い円とドットの反応が重なるか確認する。左右反転・上下のずれ・余白への反応がないこと。
3. 一人、二本の手、二人、退出、再入場を短く試す。反応の位置・遅延が子供に理解できるか見る。
4. 最初は5分、その後30分の単一シーンを確認。エラー、描画停止、異常な発熱、メモリ増加がないかを記録。
5. 操作UIの「Managerを終了」、Manager Controlの `q`、またはコンソールのCtrl+Cで全体終了する。シーンだけでEsc/qを押すとManagerは次の同一シーンを起動し得る。
6. 終了後、今回のManagerとその子PIDが残らず、もう一度同じ起動ができることを確認する。

映像は一度だけ左右反転し、その同一フレームを認識と表示に渡す。表示余白・倍率のレイアウトも同一の値を使い、指先は表示されたカメラ領域内へ変換する。これはコード/自動試験での保証であり、表示DPI・ドライバー・実カメラ遅延を含む実機目視の代わりにはならない。

## 未完了と失敗時記録

- 確認済み: 既存映像用Pythonのpreflight、実C922nの取得、初回描画通知、短時間の3回切替と正常終了。その後の露出補正では30秒無中断を確認。補正後の実機切替反復・USB復帰は別途確認する。
- `PB-01` は解消済み。その後Codexのlean-ctx連携を解除し、通常ツールから既存映像用Pythonのpreflightを再確認した。現在の実行方法と解除範囲は[解除・整合性記録](LEAN_CTX_REMOVAL_20260906.md)を参照。PATHのPython 3.11には映像用依存がないため、上の実行環境を指定する。
- `HUMAN_CHECK_REQUIRED`: 実映像と指先の5点一致、複数人・子供の遊びやすさ、30分、切替反復、USB再接続、MacBookのPAN操作。短時間の成功だけでは合格としない。
- 操作UIからの実機適用・復元・プレビューJSON保存・Next・終了をAcer内で確認済み。MacBook通信、保存値での再起動後の画角・見た目は別途確認する。
- 30分の基本動作確認後、大人がC922n切断→再接続を確認する。P1 #3は疑似カメラによる再取得・停止試験に通過したが、実USBでの復帰は未確認。12時間試験は基本確認と切替反復の後に行う。

失敗時は、preflight JSON、起動から終了までのコンソール、Camera diagnostic、各制御イベントとPID、画面サイズ・DPI、C922nのUSB接続、試した人数、期待した反応と実際の反応を残す。共有する記録から操作URLのトークンを除く。録画はこのツールでは自動取得しない。

## ロールバック

まずManagerを通常終了する。カメラ調整だけを戻す場合は [OPERATOR_PANEL.md](OPERATOR_PANEL.md) の手順で変更前の値を適用・保存する。候補全体を戻す場合は、試す前の実行場所・設定から起動し直す。Gitの共有履歴を消す操作は不要。候補ブランチの変更を戻す必要がある場合は、作業ツリーを確認して対象コミットを `git revert` する。mainへの統合はまだ行っていない。
