# 最初の1シーンを Acer + C922 で試す

対象は `finger_colorfull_dots_acer.py` → `finger_colorfull_dots_2.py`。候補ブランチは `codex/rebirth2026-production-candidate`。現段階は人間の実地確認前であり、安定版ではない。

## 起動

1. AcerにC922を接続する。別のシーンやTouchDesignerがカメラを使っている場合は、その作業を保存して通常終了する。
2. 既存シーンを動かしているPython環境を指定する。依存関係を勝手に更新しない。
3. このリポジトリの `Start Kids Test.cmd` を実行する。既定はリポジトリ内 `.venv`、なければPATHの `python`。`KIDZDISCO_PYTHON` の指定が最優先。

PowerShellで既存の映像用環境を指定する例（このAcer上で存在を確認したパス。今回の候補の実行確認は未完了）:

```powershell
$env:KIDZDISCO_PYTHON = 'C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe'
& '.\Start Kids Test.cmd' --check
& '.\Start Kids Test.cmd'
```

`--check` は依存ライブラリとMediaPipe Hands APIを確認し、カメラやウィンドウを開かない。結果は `test_reports/kids_preflight_*.json`。起動成功を意味する検査ではない。

通常起動時は試験IDごとのログ/メトリクスを `test_reports/kids_trial_*/` に保存する。30分で止めるには `Start Kids Test.cmd --duration-minutes 30`。20回切替と12時間試験の準備は [ENDURANCE_TEST_PLAN.md](ENDURANCE_TEST_PLAN.md) を参照。12時間試験はまだ開始していない。

直接起動する場合:

```powershell
python manager.py --config configs/kids_test_acer.json
```

1シーンだけを起動し、先読み・ジェスチャー切替・遷移演出を無効にしている。映像はAcerのプライマリ画面。Managerが物理カメラを1つだけ所有し、子シーンはその共有メモリへ接続する。C922名を特定できなければ停止する。候補プロファイルは1280×720、MJPG、30fpsであり、実測値は起動ログのCamera diagnosticで確認する。

## 子供が遊ぶ前の確認

1. 起動ログに `READY`、`START`、`START_ACK`、正の `frame_id` を持つ `FIRST_FRAME` が順に出る。
2. 映像がC922の実映像であることを確認。画面の中央、左上、右上、左下、右下で指先に白い円とドットの反応が重なるか確認する。左右反転・上下のずれ・余白への反応がないこと。
3. 一人、二本の手、二人、退出、再入場を短く試す。反応の位置・遅延が子供に理解できるか見る。
4. 最初は5分、その後30分の単一シーンを確認。エラー、描画停止、異常な発熱、メモリ増加がないかを記録。
5. Manager Controlの `q` で全体終了する。シーンだけでEsc/qを押すとManagerは次の同一シーンを起動し得るため、全体終了にはManager側の `q` またはコンソールのCtrl+Cを使う。
6. 終了後、今回のManagerとその子PIDが残らず、もう一度同じ起動ができることを確認する。

映像は一度だけ左右反転し、その同一フレームを認識と表示に渡す。表示余白・倍率のレイアウトも同一の値を使い、指先は表示されたカメラ領域内へ変換する。これはコード/自動試験での保証であり、表示DPI・ドライバー・実カメラ遅延を含む実機目視の代わりにはならない。

## 未完了と失敗時記録

- `HUMAN_CHECK_REQUIRED`: 実C922の取得、実映像と指先、子供の遊びやすさ、30分、終了→再起動。まだ合格と記録していない。
- `PERMISSION_BLOCKED PB-01`: エージェントから既存映像用Pythonを実行する操作がフックに拒否された。PATHのPython 3.11は映像用依存が不足し、そのままでは起動できない。既存環境の `--check` を人間が実行して結果を確認する。
- 30分の基本動作確認後、大人がC922切断→再接続を確認する。P1 #3は疑似カメラによる再取得・停止試験に通過したが、実USBでの復帰は未確認。12時間試験は基本確認と切替反復の後に行う。

失敗時は、preflight JSON、起動から終了までのコンソール、Camera diagnostic、各制御イベントとPID、画面サイズ・DPI、C922のUSB接続、試した人数、期待した反応と実際の反応を残す。録画はこのツールでは自動取得しない。

## ロールバック

まずManagerを通常終了する。今回の候補を試す前の実行場所・設定から起動し直す。Gitの共有履歴を消す操作は不要。候補ブランチの変更を戻す必要がある場合は、作業ツリーを確認して対象コミットを `git revert` する。mainへの統合はまだ行っていない。
