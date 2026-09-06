# Acer / C922n 実行環境と短時間試験

**最新の優先順位:** 部屋の暗さを含むFPSの追加調査はユーザー指示で後回し。露出・ズームは現場でMacのUIから調整する導線を優先し、今の作業とMac接続準備を並行する。以下は既に完了した観測であり、暗所の影響だけで全事象を説明した記録ではない。

**09:30の追加確認:** 初回フレーム取得後に露出-5が-4へ戻る現象を再現し、取得後の1回補正・再読戻しを実装。実Managerで30秒、約30fps、途中終了なし、正常終了を確認。回帰84件通過。[露出戻りの再現と修正記録](C922_EXPOSURE_DRIFT_20260906.md)を最新の結果とする。下記16/30fpsの「原因未確定」は切り分け途中の履歴。

**2026-09-06 08:54の環境更新:** Codexのlean-ctx連携を解除し、カメラを開かないpreflightを再確認した。[解除・整合性記録](LEAN_CTX_REMOVAL_20260906.md)を参照。解除作業自体を新たな実機合格として数えない。解除前の許可リスト修正と、その後のUI・実機試験は以下で時点を分けて記録する。

## 許可リストの修正

ユーザーの「これを修正していいよ、やって」に基づき、lean-ctx公式CLIの `allow` で次の実行ファイルを1件だけ追加した。

`C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe`

- 設定: `C:\Users\go\.config\lean-ctx\config.toml`
- 修正前バックアップ: `C:\Users\go\.config\lean-ctx\config.toml.pre-kids-20260906.bak`
- 差分は `shell_allowlist_extra` の1行だけ。shell gating、path jail、secret defenseは有効のまま。
- 既存Python 3.12.10でpreflight成功。NumPy 2.2.6、OpenCV 4.12.0.88、pygame 2.6.1、MediaPipe 0.10.14、screeninfo 0.8.1、pygrabber 0.2。パッケージの変更なし。
- `test_reports/kids_preflight_20260906_081533.json` が証拠。**PB-01は解消した。** 新規 `.venv-kids-test` を許可・使用していない。
- 設定を戻す場合は、現行ファイルに後続変更がないかバックアップとの差分を確認し、今回追加した実行ファイルの行だけを削除する。

## 実機名と参照した別タスク

ユーザー訂正: 「aサージ機＝Acer」「cp22n＝C922n USB camera」。Windowsの検出名は `c922 Pro Stream Webcam`、今回のDirectShow番号は1。番号を固定せず名前で選択する。

- `rebirth2026 Sol 再開` (`01a06293-b8d9-7832-b177-fcc674669de4`): 1280×720 / MJPG / 30fps / exposure=-5 の過去の実測記録。
- `rebirth2026_Terra` (`01a04d1b-c745-7dd1-bd2e-97d54fd7231b`): 同条件で実測29.99fps、候補の明るさ/ゲインを評価した記録。
- `StreamDiffusionTD overlay TOE作成` は要求と設計の参考であり、カメラの実測証拠としては使わない。
- `C:\rebirth2026\src\rebirth_core\camera.py` の設定順と `C:\rebirth2026\config\mode\venue.json` の露出-5を実ファイルで照合した。別プロジェクトの番号2、Bridgeの所有権、TOE、明るさ/ゲイン設定をこちらへそのまま移植していない。

## 今回の実測

|試験|結果|ローカル証跡|
|---|---|---|
|修正前30秒|YUY2、約8fps。実カメラ→MediaPipe→pygame→FIRST_FRAME→正常終了|`test_reports/kids_trial_20260906_081624_851995600/`|
|MJPG再適用後30秒|MJPG 1280×720、約16fps。初回描画・正常終了|`test_reports/kids_trial_20260906_081900_570266700/`|
|露出-5＋3回切替|要求/読戻しとも-5。4回のFIRST_FRAME、切替3回、exit 0。カメラは約16fpsのまま|`test_reports/kids_trial_20260906_082315_963110200/`|

OpenCVのDirectShowはサイズ/FPSの変更時にFOURCC指定なしで再構成する経路がある。最後にMJPGを再適用する変更で、実際の形式がYUY2からMJPGへ変わった。[OpenCV 4.12.0実装](https://github.com/opencv/opencv/blob/4.12.0/modules/videoio/src/cap_dshow.cpp#L3184)

露出の事前読取は-4、gain=107、brightness=112。露出-5を専用JSONで明示し、適用値を照合する。未指定なら変更しない。再取得時も同じ指定を通す。露出はドライバーに残る場合があるため、元の-4へ戻す必要があれば次の起動設定で明示する。明るさとゲインは変更していない。

Rebirthと同じpygrabber/IAMStreamConfig方式を診断だけで比較しても、交渉30.00003fpsに対して実測16.14fpsだった。**露出だけを原因とする仮説は、今回の実測で成立しなかった。30fps達成とは扱わない。** この比較用コードは無視対象の `test_reports/` に置き、本番カメラ実装を別方式へ交換していない。画像・ランドマークは保存していない。

自動回帰テスト66件通過。追加した検証はDSHOW再構成後のMJPG保持、FPSの観測区間の計数、露出の未指定/拒否/読戻し不一致、環境優先と再取得への継承。短時間の機構確認であり、30分・12時間・USB抜去・複数人・パネル上の5点座標一致は未合格。

## 操作UIと追加の実測（08:45〜08:57）

MacBook向けの共通ブラウザUIを追加した。露出・ズームをスライダーまたは数値で編集し、適用時にカメラの取得スレッドが設定・読戻しを行う。物理カメラの所有はManagerだけ。JSON保存は適用成功後だけ可能で、同時保存・古い適用番号による上書きを拒否する。未対応値の復元と、その読戻しがNaNのときの未確認表示も自動試験に含む。

|追加試験|確認した結果|ローカル証跡|
|---|---|---|
|5分のManager試験|起動時29.96fps、その後の取得フレームも概ね30fps。途中でdotsが1回終了して再起動。最後は `duration_reached / exit_code=0`|`test_reports/kids_trial_20260906_084543_686707500/`|
|ブラウザ→実C922n|露出 -5→-6、ズーム176→180を適用。要求と読戻しが一致。スライダーのキー操作で-5/176へ復元し、再び一致|`test_reports/operator_ui_20260906_085110/`、`operator_ui_preview.stdout.log`|
|JSON保存|復元後の-5/176をプレビュー用JSONに保存。他のカメラ/シーン設定を維持|`test_reports/operator_ui_preview.json`|
|UIのNext|Mandala→dots、dots→Mandalaの2回がFIRST_FRAME後に切替。Managerの共有カメラ名を維持|同UI試験の制御イベント|
|UIの終了|`operator_quit / exit_code=0`。取得失敗・再取得はともに0。Manager・当該子PIDの残留なし|同UI試験の `runtime.jsonl`、終了後のOSプロセス確認|
|保存値によるMandala単独再起動|露出-5/ズーム176のJSONを再読込しFIRST_FRAME。約10分後 `duration_reached / exit_code=0`。途中2回 `launcher_exit_code=0` を記録して再起動した|`test_reports/mandala_preview_20260906_0901/`|

ブラウザのレイアウト、入力、適用中の無効化、読戻し表示、保存をAcer内のブラウザで確認した。実機試験の認証はloopbackだけに限定した一時テスト用起動で行い、通常起動のランダムトークン方式は保持した。一時の起動スクリプト・認証値・ログは `test_reports/` に置き、Gitへ含めない。通常の `kids_test_acer.json` のシーンリストやズーム値はこのUI試験で変更していない。

**30fpsは今回の再起動で観測した値であり、以前の約16fpsとの差の原因は未確定。** Mandala単独プレビューは再び16.28fpsで起動したが、同じ露出-5/ズーム176を取得スレッドへ再適用すると、その後の取得が10秒300枚≒30fpsになった。露出・ズーム・モード・適用時点のどれが原因かはまだ分離していない。

初回dotsは旧試験でFIRST_FRAME後約27秒、UI試験で約39秒に終了した。Tracebackもカメラ障害も残っていないが、終了キー操作・正常終了・ネイティブ異常の区別はできない。UI試験では後のMandalaにも操作要求外の終了があった。追加した `scene_exit` 観測では、Mandala単独試験の2回の終了はlauncher code 0だった。これは操作理由まで特定する証拠ではない。途中で再起動しているため、5分/10分試験を単一シーン無中断の合格にはしない。

テスト起動の初回はコマンド監視を1秒、次は60秒に設定したため、出力がない期間に監視が終了した。Manager本体はその後も動いていた。初回は今回起動したManager PIDを照合して停止し、そのJobの子も消えたことを確認。後者は5分の期限で正常終了した。以後は標準出力/標準エラーをローカルログへリダイレクトして起動し、試験の終了期限はManagerが持つ形にした。カメラ使用中に誤って重ねた起動は取得失敗で終了しており、カメラの二重所有成功とは扱わない。

## 残る確認

- MacBookからの実通信はPANのIPv4が未接続のため未確認。[操作手順](OPERATOR_PANEL.md) に明示PANアドレスでの起動を記載した。
- 実映像の5点座標一致、子供・複数人、30分無中断、20回切替、USB復帰、Xiaomi、12時間はHuman Check Required。
- ユーザーの共通透過率スライダー要望は [調査メモ](OPACITY_CONTROL_PLAN.md) に記録。透過対象は確認中で、実装済みとは扱わない。
- `finger_mandala_acer.py` は現行 `_2.py` のプレビュー。看板候補 `_3.py` への変更・本番採用・複数人仕様の承認を含まない。
- 09:30の試験後、別作業のTouchDesignerが起動していることを確認。追加の物理カメラ再取得試験は競合しないタイミングで行う。今回のタスクから別作業を停止していない。
