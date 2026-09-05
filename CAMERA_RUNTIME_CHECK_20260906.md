# Acer / C922n 実行環境と短時間試験

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

## 次の作業

ユーザー追加要望: MacBookのブラウザUIから露出・ズーム等を調整し、JSONへ保存できること。物理カメラはAcerのManagerが所有し続ける。PANのIPv4は今回未接続で、MacBookからの接続確認はまだできていない。UIの実装と、適用/保存/再取得の検証を次に行う。
