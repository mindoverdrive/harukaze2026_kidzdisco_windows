# Codexのlean-ctx解除と整合性確認

更新: 2026-09-06 08:54 JST。ユーザーの「lean-ctxを抜いてもいいよ」「そのあとの整合性もとって」に基づく作業。

## 現在の状態

Codexのlean-ctx MCP、PreToolUse等のフック、強制利用指示、スキル登録を解除した。通常のCodexツールと既存のRTKを使う。過去の会話やこのリポジトリにあるlean-ctxの利用指示・実行拒否は当時の記録であり、現在の実行要件ではない。

PC全体のアンインストールは行っていない。lean-ctxの実行ファイル、保存データ、Gemini／Antigravity等の連携は残している。一括アンインストールによる他のアプリや保存データへの影響と、`unwrap`による導入前の全設定への巻き戻しを避け、Codexの登録だけを除去した。全lean-ctxプロセスの停止やCodex再起動は実行していない。

既に開いている会話には読み込み済みのMCP一覧・旧指示が残る場合がある。通常ツールでの実行は確認済み。アプリのMCP一覧まで更新する場合は、進行中作業の区切りでCodexを再起動する。旧ツールが見えることを再導入の理由にしない。

## 変更した登録

|対象|変更|
|---|---|
|`C:\Users\go\.codex\config.toml`|`mcp_servers.lean-ctx`とそのenv、削除したフックに対応するtrust記録5件を削除。他のMCP・設定はTOMLの構造比較で保持を確認|
|`C:\Users\go\.codex\hooks.json`|lean-ctxのフック5件を除去。元の登録は全てlean-ctxのものだったため現在は空のhooks|
|`C:\Users\go\.codex\AGENTS.md`|lean-ctxの管理ブロックを削除し、通常ツールとRTKを使う現行方針を記載|
|`C:\Users\go\.codex\LEAN-CTX.md`、`skills\lean-ctx`|バックアップ先へ退避。通常の指示・スキル探索先から除去|
|`C:\Users\go\Documents\PowerShell\Microsoft.PowerShell_profile.ps1`|lean-ctx専用だった3行のフックを除去。別のプロファイル設定は存在しなかった|
|`C:\Users\go\.config\lean-ctx\config.toml`|公式CLIで`shadow_mode`をtrueからfalseへ変更。解除作業中のnative tool強制拒否を止めた。この値はlean-ctxのグローバル設定であり、Codex以外にも適用される|

`features.hooks`全体や他の安全設定を無効化する変更は行っていない。プログラム本体、Python環境のパッケージ、カメラ設定、TDや映像プロセスにはこの作業で変更を加えていない。

追加の整合性確認で、元の春風チェックアウト `C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows` にも必須規約が残っていた。既存の未コミット内容を`backups\lean-ctx-removal-20260906\scratch`へ保存してから、AGENTS・README・共通規約・作業手順・RTK/Graphifyの手順・スキル台帳を更新した。ローカルlean-ctxスキルも退避し、有効なスキル数は18から17になった。元の導入検証やライセンス情報は履歴として保持した。アプリケーションのPythonソースや既存検証器のロジックは変更していない。

## 解除後の検証

|確認|結果|
|---|---|
|通常ツールでのグローバル設定、別リポジトリ、スキルの読み取り|成功|
|既存映像用Python 3.12.10で`start_kids_test.py --check`|成功。依存6項目を確認、failuresは空。`test_reports/kids_preflight_20260906_085441.json`|
|`python -m unittest discover -s tests -p test_camera_profile.py -v`|9件成功。以前拒否された`-p`を含む実行が通る|
|`py -0p`|成功。インストール済みPython一覧を取得|
|`.venv-kids-test\Scripts\python.exe --version`|成功、Python 3.11.9。この環境への映像依存の導入や使用切り替えは行っていない|
|`C:\rebirth2026\.venv\Scripts\ruff.exe --version`|成功、Ruff 0.16.1。ここで確認したのは実行可否であり、別プロジェクトのlint合格ではない|
|設定構文・他の設定の保持|JSON/TOML解析と解除前後の構造比較で確認|
|元の春風チェックアウトのスキル整合性|17スキルのファイル一覧・ハッシュ・参照・依存関係を既存検証器で確認。検証器の既存テスト8件も成功|
|現在の資料とローカル登録|資料8ファイルの現行記録へのリンクを確認。関係する3チェックアウトのローカルMCP登録・強制利用指示に未解消項目なし|
|差分の形式|対象の文書・スキル変更に対する`git diff --check`成功|

上記テストは実カメラを開かない。カメラのようなログを出す単体テストは疑似入力を使用しており、今回の実機合格には数えない。WindowsでPythonから日本語を含む確認結果を出す際は、当該コマンドに`-X utf8`を指定して出力文字コードをそろえた。

## 保留の扱い

PB-01は解消済み。08時台前半の実シーン短時間試験の証拠は[実機記録](CAMERA_RUNTIME_CHECK_20260906.md)、今回の追加証拠は上記preflightで確認する。

子供の操作、5点の座標一致、30分単一シーン、切り替え反復、USB再接続、Xiaomi、12時間耐久は、それぞれの最新の実機記録で判定する。lean-ctx解除をこれらの合格と扱わない。約16fps、TD接続、NVML/MUX、保存承認等の別原因も解除だけで解決したとは扱わない。過去に止まった別タスクのミッションをこのサイド会話から再開してはいない。

## バックアップと復旧

退避先: `C:\Users\go\.codex\backups\lean-ctx-removal-20260906`

`manifest.json`に変更対象・変更前後のSHA-256・退避先を記録した。Codex設定、hooks、AGENTS、PowerShellプロファイルの変更前コピーと、退避した指示ファイル・スキルを保持している。lean-ctx設定のコピーはnative opt-out後のもの。元の`shadow_mode=true`はmanifestに別記した。

復旧時は対象ファイルに後続変更がないか照合し、変更がある場合はlean-ctxの登録差分だけを戻す。古いconfig.tomlを無条件で全体上書きしない。グローバルAGENTSへの現行方針追記を含め、最終検証時のハッシュも退避先に記録する。再登録・再起動はユーザーが復旧を求めた時に行う。
