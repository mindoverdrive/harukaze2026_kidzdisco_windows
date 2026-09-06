# Rebirth 2026：単一シーン候補と共通基盤の引き継ぎ

## 現在の到達点

**最新のユーザー方針:** 部屋の暗さが低fpsに影響している可能性を踏まえ、FPSの追加調査は後回しにする。露出・ズームをMacのUIから現場で調整し保存する導線を優先する。暗さを唯一の原因と断定せず、既に検証した指定値補正は保持する。現在の作業を止めず、ユーザーが準備できるMacとの接続確認を並行する。

**最新チェックポイント:** 完了監査で、本番シーン一覧の省略時に7本へ広がる問題と、カメラ初期設定・解放の二重失敗で所有参照を失う問題を再現し、`40db032`・`d94ba5d`で最小修正・通常pushした。全回帰 **94件 / 9.256秒 / OK、終了コード0**。実際の `Start Kids Test.cmd --check` も既存映像用Pythonで成功した。この追加修正後の実カメラ試験は未実施。[P1完了監査](P1_CANDIDATE_COMPLETION_AUDIT_20260906.md)を現在の根拠とする。

**前段階（09:30の実機結果）:** C922nの初回フレーム後の露出戻りを再現・修正し、基準シーンで30.719秒・約30fps・途中終了なし・正常終了を確認した。当時の回帰は84件。Acer内のカメラUIも確認済み。MacBookとの実通信、透過対象、子供の操作、30分/12時間は保留。[露出補正の記録](C922_EXPOSURE_DRIFT_20260906.md)を今回の追加修正後の実機再検証とは扱わない。

**別タスクとの分担:** ユーザー報告により動的HTML作業は完了。`20260906-current-status.html`、`status_dashboard/README.md`、`status_dashboard/status_server.py`は別タスクの成果物として保持し、このチェックポイントに混在させない。MCP・フック解除は維持されている一方、旧lean-ctxスキルの再出現表示は要再確認。環境設定を再変更する根拠にはしていない。

**操作UI追加時点の到達点（2026-09-06）:** Acer内のブラウザからC922nの露出・ズームを適用/読戻し/復元し、プレビューJSONへの保存、シーン切替、Managerの通常終了を確認した。自動回帰77件通過。MacBookのPAN通信、子供の操作、30分無中断、12時間は未確認。起動ごとの約16/30fps差と操作要求外のシーン終了は未確定として残す。最新の手順は [操作UI](OPERATOR_PANEL.md)、実測は [実機記録](CAMERA_RUNTIME_CHECK_20260906.md)。以下の63件/66件は前段階の履歴。**

**2026-09-06 08:54の環境更新:** Codexのlean-ctx連携を解除し、既存映像Pythonのpreflightを再確認した。元の春風側も含む関連テストは計17件。PB-01は解消済み。現在のツール運用と解除範囲は[解除・整合性記録](LEAN_CTX_REMOVAL_20260906.md)を参照。解除作業自体はカメラ試験を追加していない。後続の実機/UI試験は別の項目として記録する。

**最初の候補は `finger_colorfull_dots_acer.py`。専用の起動入口、映像/指先の共通座標変換、共有カメラ、起動同期、終了処理、試験ログを実装し、自動テスト63件が通過した。実C922の映像を出して子供が遊べることはまだ確認できていない。**

**08時台の更新: ユーザー許可でlean-ctxへ既存映像Pythonを1件だけ追加し、PB-01を解消した。preflightと実C922nでの30秒起動・3回切替が成功。自動回帰は66件通過。以下の初回報告に対する更新・ログ・残る約16fpsの問題は [実機確認記録](CAMERA_RUNTIME_CHECK_20260906.md) を正とする。子供の操作確認・30分・12時間は未合格。**

対象ブランチは `codex/rebirth2026-production-candidate`。基点は `260ee87`。main/stableへの統合、force push、本番昇格は行っていない。別ディレクトリで動いていた `finger_mandala_3_test.py` と関連するユーザープロセスは停止していない。

## 最新優先との整合

ユーザーの最新指示に従い、7シーン全体の演出よりも「Acer + C922でまず1シーン」「映像と操作位置を構造的に一致」を先にした。名称の音声誤認は、実機OSのAcer Nitro AN515-58とc922 Pro Stream Webcamの存在確認を踏まえて解釈した。OSのStatus=OKを映像取得成功とは扱っていない。

人がいないときは波の中心がゆっくり動く。白い指先マーカーは現在検出した手だけを示し、退出後には残さない。色と波の既存描画を維持し、時間変化を実時間に合わせた。画面全体を突然リセットする処理はこの基準シーンに追加していない。

`finger_mandala`の代表候補が `_3.py`、現在のAcerラッパーが `_2.py`という未確定の対応は維持する。目視で選ばれていない実体に3人対応・人別色・全体演出を一括移植していない。妖精ガイド、桜遷移の一新、他シーンのリッチ化は品質/ファイル選定が残る。

## 変更と検証

|段階|主な変更|実施した検証|
|---|---|---|
|P1 #2|production候補を明示リスト化。ラッパー/元source/acer profile/存在/構文/パスを起動前に検証。一覧省略による暗黙の補完を禁止|対象外混入、重複、パス逸脱、欠落、誤profile、不正設定を拒否。実JSON入口から省略/null/空をカメラ生成前に拒否|
|P1 #6|初期化開始時から取得済み資源の解放を登録。終了処理を独立実行し、停止失敗時の参照を保持。VideoCapture取得直後から所有を登録|7シーンの実ソースで初期化失敗を注入。release失敗時も後続の資源を解放。カメラ初期設定とreleaseの二重失敗後もcapを保持|
|P1 #9|Managerの解決したcamera値を子へ継承。Managerが物理カメラを所有し、管理下の子の物理fallbackを禁止|環境優先、profile上書き防止、名前/番号の矛盾、共有必須を検証|
|P1 #1|READY→START→START_ACK→FIRST_FRAME。受信準備と描画処理成功を分け、初回成功まで旧シーンを保持|実TCP/実runner/分割JSON/接続断/期限/別カメラ/描画エラー。固定sleepだけで同期しない|
|P1 #3|再取得失敗後も継続。停止イベント、再試行間隔、フレーム鮮度、固有共有メモリ名と所有セッション。旧capの解放成功まで新規openを禁止|実共有メモリとスレッド＋疑似captureで切断→取得失敗→復帰、read/open中の停止、release失敗→成功後の再取得を検証|
|Windows追加|venv中継PIDを識別し、所有Jobで実Pythonと子プロセスを管理|実OSで中継起動、READY前の子、親のみ終了、Job close、無関係PID拒否。ユーザーの既存プロセスは対象外|
|1シーン|専用config、C922の名前照合、依存preflight、同一mirror/layoutによる画像と指先の投影|中央/四隅/異なる縦横比/1px越境、検出→退出→フレーム喪失を検証|
|試験準備|時間指定終了、切替回数指定、制御/子出力/資源ログを容量制限付きで保存|カメラなしの実Managerで3回切替、初回フレーム後から計時、ログ排出/世代保存、Windowsカウンター100回照会|

P1初回報告時の実行コマンドは `python -m unittest discover -s tests -q`、結果は **63 tests / OK**。UIと初回設定補正の段階は84件、今回の一覧省略・二重失敗修正後は **94 tests / 9.256秒 / OK、終了コード0**。関連Pythonの構文検査と `git diff --check` も通過した。回帰後の46ファイルのSHA-256は `test_reports/p1_completion_sources_20260906.json` に保存し、現在のソースと一致した。リポジトリ直下の旧テストを無差別に実行していない。

OpenCV/NumPy/MediaPipe/pygame/pygfxの描画処理は疑似実装を用いた試験であり、GPU描画・C922実取得の証拠ではない。物理カメラを開かずに、Windowsのプロセス/Job/カウンター、TCP、共有メモリ、スレッド、数値変換を実行した。

## コミット

各段階を同じ候補ブランチへ通常commit/pushした。

|コミット|内容|
|---|---|
|`fe3eba7`|本番候補シーンを明示リストで検証|
|`83a399a`|異常終了でも実行資源を段階的に解放|
|`2af6e06`|カメラ設定をManagerの解決値に統一|
|`0688213`|初回描画確認まで旧シーンを保持する起動同期を追加|
|`d95de84`|C922の単一シーン実地テスト入口と座標一致を整備|
|`43cba36`|カメラ再取得とフレーム鮮度を管理し停止時の競合を修正|
|`bdfe9ee`|初期化途中の解放と本番入口の検証を補強|
|`6aec719`|Windowsの中継Pythonを識別しシーン子プロセスをJobで管理|
|`0b8dafb`|基礎試験の自動終了と切替反復・資源ログを準備|
|`567b32c`|ログ設定失敗時のプロセス参照保持、試験引数の誤記拒否、初回成功後からの試験計時、初回の最終引き継ぎ|
|`140ec05`|C922nのMJPG再適用と露出指定、実機preflightと短時間切替|
|`45c1d29`|Mac向けカメラ調整UI、保存検証、実機引き継ぎ。回帰77件|
|`c9cc221`|初回取得後の指定値補正・解放、回帰84件と実機30秒の記録。FPS追加調査は後回し|
|`40db032`|本番シーン一覧の省略/null/空をカメラ取得前に拒否。JSON入口と明示順序の試験を追加|
|`d94ba5d`|カメラ取得直後に所有を登録。初期設定とreleaseの二重失敗でも保持し、解放成功後だけ再取得。全回帰94件|

## 最初の起動と自動試験手順

まず [KIDS_TEST_START.md](KIDS_TEST_START.md) に沿って既存映像用Pythonを選ぶ。その環境を実行できる人間のPowerShellで、カメラを使う別作業を保存・終了してから以下を進める。

```powershell
$env:KIDZDISCO_PYTHON = 'C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe'
& '.\Start Kids Test.cmd' --check
# preflight成功後、まず5点の座標一致と短い操作確認
& '.\Start Kids Test.cmd'
# その後に30分試験
& '.\Start Kids Test.cmd' --duration-minutes 30
# 30分の確認と分けて20回切替
& '.\Start Kids Test.cmd' --switch-every 20 --switch-count 20 --duration-minutes 30
```

このパスは既存映像用Pythonであり、その環境でpreflightと今回の候補の実C922n起動を確認した。新しく作った `.venv-kids-test` は映像用依存未導入で、本候補の実行環境へ切り替えていない。

`Start Kids Test.cmd` は専用configの1シーンだけを使い、先読み、ジェスチャー切替、遷移を無効にする。表示先はAcer primary。要求カメラ値は1280×720/MJPG/30fpsの候補値。C922の名前を特定できなければ停止する。Manager Controlのq、またはコンソールCtrl+Cで全体終了する。

12時間試験のコマンド、記録項目、暫定合格条件は [ENDURANCE_TEST_PLAN.md](ENDURANCE_TEST_PLAN.md)。**12時間は準備だけで、開始していない。**

## 保留一覧と次の判断

|状態/ID|残っていること|根拠/次の確認|
|---|---|---|
|RESOLVED PB-01|映像用Pythonの実行とimport確認|ユーザー許可後に公式CLIで実行ファイルを1件追加。既存環境のpreflightと実シーン起動を確認。詳細は実機確認記録|
|HUMAN_CHECK_REQUIRED H-01|5点の映像/指先一致、子供が遊べること|実C922n取得と初回描画通知は確認済み。パネル上の座標、表示DPI、体感遅延、子供の操作は未確認|
|HUMAN_CHECK_REQUIRED H-02|30分単一シーン、20回切替、USB復帰、終了後再取得|疑似入力での機構試験は通過。実カメラ/熱/ドライバー待ち/資源の長時間傾向は実機が必要|
|HUMAN_CHECK_REQUIRED H-03|Xiaomi L32M8-A2TWNへの全画面とGPU2シーン|表示モード、DPI、GPU負荷、実パネルの表示品質が未確認|
|HUMAN_CHECK_REQUIRED H-04|採用する正確な各sceneと演出品質|`finger_mandala_3.py`と現行 `_2.py` 等の選定、個人と左右の手の対応、妖精ガイド、桜遷移の見た目を確定する必要がある|
|HUMAN_CHECK_REQUIRED H-05|12時間再起動なし|まず基礎試験を人間が評価。試験コマンドを用意したことを耐久合格にしない|
|設計/実機保留 H-06|MacBookとの通信、Python↔TouchDesigner切替、一発差し替え|露出・ズームの共通UIはAcer内で確認済み。接続方式はホットスポット/Bluetooth PAN/同じWi-Fiから選択待ち。MacBook通信、採用runtime TOE、Xiaomi、カメラ所有権移譲とrollbackは未確認|
|確認待ち H-07|Macから共通透過率スライダー|ウィンドウ全体かカメラ背景かを確認中。[調査メモ](OPACITY_CONTROL_PLAN.md)に接続点と実機確認を整理。未実装|
|追加確認 H-08|露出補正後の継続動作、操作要求外のシーン終了|初回取得後の露出戻りは再現・修正し30秒で約30fps。再取得は疑似試験済み、実USBは保留。以前のMandala単独10分の途中2回はlauncher code 0、操作理由は未確定。FPSの追加追究は後回し、露出は現場でMacから調整|

現在、未解決のPermission Blockedや、コード上で解決不能として放棄したP1はない。実機合格がないため、P1の「実運用上の完全解決」とはしていない。native open/read/releaseの停止、実USB復帰、長時間資源の増加など、追加実機データを必要とする項目は上表のHuman Check Requiredとして残す。

次の実機順は **finger_colorfull_dots_acer → finger_grid_interaction_acer → particle_storm_acer**。入口の座標/因果、CPUと複数手、WGPU/モデル/描画資源を順に確かめるため。最初の単一シーンが最優先であり、後の2本を本番採用したことにはしない。

## ロールバック

1. 候補Managerを通常終了し、今回のJob/PIDと画面が消えたことを確認する。
2. それまで使用していた別ディレクトリの実行方法へ戻す。今回、その稼働資産を変更していない。
3. ソースを比較する場合は `260ee87` を基点とする。共有履歴を消すreset/force pushではなく、必要な候補コミットをgit revertするか、別のcheckoutで比較する。未保存変更がある作業ツリーで破壊的な切替をしない。
4. 共有プロトコルはHARUCAM2へ変更したため、異なる版のManagerと子シーンを混在させない。

## 変更ファイル一覧

基点 `260ee87` から本報告までの55ファイル。Git差分と下記一覧の過不足がないことを照合した。Acerラッパー7本は本文を読んだが変更していない。`.shared_camera_session.json` は生成物としてGit追跡を解除し、元のローカルファイルを残した。

```text
.gitignore
.shared_camera_session.json (Git追跡解除)
CAMERA_RUNTIME_CHECK_20260906.md
C922_EXPOSURE_DRIFT_20260906.md
ENDURANCE_TEST_PLAN.md
KIDS_TEST_START.md
LEAN_CTX_REMOVAL_20260906.md
OPACITY_CONTROL_PLAN.md
OPERATOR_PANEL.md
P1_CANDIDATE_COMPLETION_AUDIT_20260906.md
PRODUCTION_CANDIDATE_PROGRESS.md
PRODUCTION_CANDIDATE_REPORT_20260906.md
README.md
RECHECK_AUDIT_20260906.md
REBIRTH_IPHONE_HANDOFF_2026-09-05.md
Reverse Ubers iPhone Handoff .md
Start Kids Test.cmd
camera_controls.py
config.json
configs/kids_test_acer.json
display_utils.py
finger_colorfull_dots_2.py
finger_grid_interaction_2.py
finger_mandala_2.py
fractal_moving_2.py
manager.py
operator_panel.html
operator_panel.py
particle_storm_2.py
runtime_diagnostics.py
saturn_particles_2.py
scene_control.py
scene_profile_runner.py
scripts/start_kids_test.py
shared_camera.py
spider_cursor_2.py
tests/fixtures/handshake_body.py
tests/fixtures/handshake_launcher_acer.py
tests/fixtures/handshake_scene_acer.py
tests/test_camera_coordinates.py
tests/test_camera_first_frame_controls.py
tests/test_camera_profile.py
tests/test_camera_reconnect.py
tests/test_cleanup.py
tests/test_first_frame_render.py
tests/test_kids_test_launch.py
tests/test_operator_panel.py
tests/test_production_playlist.py
tests/test_runtime_diagnostics.py
tests/test_runtime_validation.py
tests/test_scene_control.py
tests/test_scene_resources.py
tests/test_scene_switch.py
tests/test_windows_launcher.py
windows_process.py
```

無視対象のローカル実行物は `test_reports/`、`__pycache__/`、新規 `.venv-kids-test/`。別タスクの動的HTML、`status_dashboard/`、`TD_BUSINESS_RESEARCH_20260906.md` は今回の変更一覧・コミットに含めない。モデルファイルは存在とサイズまで読み取り、変更していない。requirementsや既存映像環境のパッケージ更新、本番データ/TOE変更は行っていない。

## 操作UIの追加チェックポイント

- `camera_controls.py`：カメラの取得スレッドへ最新の設定を渡す。要求/読戻し、失敗時復元、同時保存、古い設定番号、未確認の値の保存を管理。
- `operator_panel.py` / `operator_panel.html`：起動ごとの認証、明示IPv4、露出・ズームのスライダー、適用・JSON保存、Next・終了。物理カメラやカメラ映像をブラウザへ公開しない。
- `manager.py` / `shared_camera.py` / `scripts/start_kids_test.py`：起動・終了へUIを接続し、変更値をカメラ再取得へ継承。予期しないscene終了はlauncher PIDと終了コードを記録。
- `tests/test_operator_panel.py` / `tests/test_camera_profile.py` / `tests/test_runtime_diagnostics.py`：取得スレッドでの適用、認証、保存前確認、競合、復元NaN、正常/非ゼロの終了ログを確認。
- [操作手順](OPERATOR_PANEL.md)、[実機記録](CAMERA_RUNTIME_CHECK_20260906.md)、[透過率の未確定要件](OPACITY_CONTROL_PLAN.md)とiPhone引き継ぎを更新。別作業で追加された[lean-ctx解除記録](LEAN_CTX_REMOVAL_20260906.md)は保持した。

統合時の回帰は **77 tests / OK**。追加した保存競合/復元/終了ログの5テストは修正前に失敗し、修正後に通過した。途中のHTTP認証試験でWinError 10053が1回発生したが、認証を含む9テストの追加5回はすべて通過し原因未確定。無制限な試行や根拠のないネットワーク変更は行っていない。

この段階のUIを戻す場合はManagerを終了して `Start Kids Test.cmd --no-ui`。カメラ値は変更前の値を明示して復元する。コード全体を戻す場合はUI追加直前の `140ec05` と比較し、必要な候補コミットをrevertする。main/stableへは統合しない。

## 露出戻りの追加修正

UI追加は `45c1d29` へ通常push済み。その後 `shared_camera.py` のDSHOW起動/再取得に2フレームの設定確認を追加し、指定値から戻った項目だけ1回補正した。`tests/test_camera_first_frame_controls.py` の7テストとfixture調整を含む回帰は84件通過。実Managerで29.69fpsの初期診断、約30fpsの継続取得、30秒無中断・exit0・当該PID残留なしを確認した。

初回回帰のWindows Jobの単発WinError 5は再現せず、未解決の権限保留とはしていない。試験後に別作業のTouchDesignerが起動したため、追加の物理カメラ再取得は競合しない時点へ保留した。詳細・試験ID・限界は [C922_EXPOSURE_DRIFT_20260906.md](C922_EXPOSURE_DRIFT_20260906.md)。

この追加だけを戻す場合はManagerを終了して当該候補コミットをrevertし、UI段階の `45c1d29` と比較する。共有履歴を消すreset/force pushは行わない。

## P1完了監査の追加チェックポイント

`c9cc221`を読み直し、規約と仕様の独立レビューを行った。一覧省略で起動対象が増える問題、カメラの初期設定と解放が同時に失敗すると所有を失う問題を新規試験で再現し、上記2コミットで修正した。独立した再確認でも両方の所見を解消し、全94件が通過した。残る命名上の軽微な指摘は機能障害ではなく、最小変更方針で見送った。

既存映像Pythonで実際の `Start Kids Test.cmd --check` を実行し、`test_reports/kids_preflight_20260906_101821.json` に不足依存なしを記録。物理カメラ・ウィンドウを開く試験ではない。今回の追加2件を戻す比較基点は `c9cc221`、必要時は `d94ba5d` → `40db032` の順でrevertする。根拠、合格範囲、残る確認は [P1完了監査](P1_CANDIDATE_COMPLETION_AUDIT_20260906.md)にまとめた。
