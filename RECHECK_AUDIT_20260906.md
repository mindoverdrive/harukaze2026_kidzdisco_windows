# 共通基盤の再監査と最初のシーン

対象はproduction entrypoint、manager.py、scene_profile_runner.py、shared_camera.py、display_utils.py、7個のAcerラッパーとその `_2.py` 実体。推測の修正を避け、再現できたものから変更した。Acer/C922の実描画はまだ確認していない。

|重要度|箇所|確認した障害条件|最小変更と自動検証|
|---|---|---|---|
|P1|7シーンの初期化と終了|Hands生成後のカメラ例外、カメラ取得後のHands例外、GPU canvas生成後のrenderer例外では、旧コードの終了処理が未登録/未到達|標準ExitStackに取得直後の解放を登録し、初期化開始時からatexitで保証。実ソースを読み、7シーンの初期化失敗を注入して登録済み資源の解放を検証。1つのrelease失敗でも他のcallbackが実行されることを検証。|
|P1|manager.load_config|不正JSON型、負のサイズ、FPS=0、NaN期限、backendの誤記がカメラ初期化まで通る|明示的にConfigurationError。既定値への黙った復帰を防ぐテスト。|
|P1|Manager→runner→source|ラッパーだけ存在し、元ファイルがない/プロファイル名が誤っている状態でも物理カメラが先に開く|run_sceneのリテラル引数とprofile='acer'、実際にrunnerが解決するsourceの存在/構文/リポジトリ内パスを起動前に検証。|
|P1|Shared Cameraの配信設定|SHARED_CAMERA_ENABLED=falseのときManagerが物理カメラを所有したまま、子への必須共有接続情報が消える|Managerでは共有を必須とし、設定矛盾を起動前に拒否。standaloneの物理カメラ経路は変更していない。|
|P2|Managerの表示設定→Acer profile|明示した画面座標があっても、wrapperの既定primary指定が優先される|Managerに明示したgeometryをstageとして継承。1シーンconfigのDISPLAY_TARGET=primaryはその後に優先する。実Xiaomi出力/DPIはHuman Check Required。|
|P2|HeadClapMonitor|MediaPipe importがtryの外にあり、欠落時にstatusがidleのままスレッド終了|importも例外処理内に置きfailedを報告。依存欠落を注入するテスト。|
|P2|Managerの強制終了fallback|taskkill自体には時間上限がなかった|subprocess.runに終了期限を追加。無期限待ちを避ける。実ドライバー/GPUの終了保証は別。|
|P1/操作|finger_colorfull_dots_2.py|人が消えても最後の指先と白マーカーが残り、カメラ切断時も最後の画像が残る|各フレームで検出状態を更新。古いカメラ画像を表示せず、無操作中の波はゆっくり移動する中心から生成。白マーカーは実検出に限定。検出→退出→フレーム喪失の実ループを疑似入力で検証。|

ExitStackの登録は子プロセス1回の実行寿命に対応する。rendercanvasの終了には公開APIの [BaseRenderCanvas.close](https://rendercanvas.readthedocs.io/stable/api.html#rendercanvas.BaseRenderCanvas.close) を使う。GPUの内部bufferを推測したAPIで破棄していない。実GPUメモリの返却とQt/GLFWウィンドウ消失は実機観測が必要。

## 自動試験の範囲

`python -m unittest discover -s tests -q` のみを使う。リポジトリ直下にある旧 `test*.py` はカメラやGUIを開く可能性があるため、全ルートでdiscoverしない。テスト内のOpenCV/NumPy/MediaPipe/pygame/pygfxは疑似実装。TCP、runner子プロセス、共有メモリ、スレッド、数値座標変換は実行しているが、実カメラ/描画の合格を意味しない。

## 残る実機判断

- HUMAN_CHECK_REQUIRED: 本物のMediaPipe/pygameで元シーンの見え方と遊びやすさが維持されたか。無操作中の動きから人の反応へ移る見え方。
- HUMAN_CHECK_REQUIRED: C922の実取得、指先と映像の5点照合、2人、USB復帰、30分、切替反復、終了後再起動。
- HUMAN_CHECK_REQUIRED: 通常configのXiaomi座標・DPI・GPU2シーンの負荷。7候補全てを本番採用したことにはしない。
- HUMAN_CHECK_REQUIRED: ネイティブread/openが永久停止した場合のOS/ドライバー挙動。Pythonは別スレッドから競合releaseを強行せず、停止未完了を報告する。
- PERMISSION_BLOCKED PB-01: 既存映像用Pythonの実行確認。詳細はPRODUCTION_CANDIDATE_PROGRESS.md。

既存requirements.txtには全用途の依存が混在し、NumPy2/OpenCV4.12とMediaPipe0.10.14の互換性、およびPythonバージョン条件を今回の許可された環境では確認できていない。実稼働中の別環境を更新して解決したことにはしない。
