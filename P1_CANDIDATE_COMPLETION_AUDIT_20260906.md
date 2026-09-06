# Rebirth 2026：P1本番候補の完了監査

対象ゴールは、隔離ブランチ上でP1のproduction entrypoint・cleanup・camera profile・起動handshake・camera reconnectを調査、最小修正、検証、再検証、checkpoint commitし、人間がAcer／C922n／Xiaomiの実機評価を開始できる候補と、保留・起動・rollback・確認順を渡すこと。

到達段階は **人間の実機評価へ渡す本番候補**。子供の操作、Macからの通信、Xiaomi表示、実USB復帰、30分・12時間の合格や、本番昇格を意味しない。FPSの追加原因調査はユーザー指示で後回しとし、現場でMacから露出等を調整する方針を維持する。

## 現在の証拠

- ブランチ: `codex/rebirth2026-production-candidate`。監査基点は `260ee87906f91e1e4e1c20f99f8b1caf1d0754b9`。
- 最初の独立レビュー対象は `c9cc221`。未検出だった2件を再現し、`40db032` と `d94ba5d` で修正・通常pushした。
- 修正後の全回帰: `python -m unittest discover -s tests -q`、**94件 / 9.256秒 / OK、終了コード0**。
- 実際の `Start Kids Test.cmd --check` を、既存の映像用Python 3.12.10で実行し終了コード0。numpy 2.2.6、OpenCV 4.12.0.88、pygame 2.6.1、MediaPipe 0.10.14、screeninfo 0.8.1、pygrabber 0.2を確認。カメラ・ウィンドウは開いていない。
- 回帰ログ: `test_reports/p1_completion_regression_20260906.stdout.log` / `.stderr.log`。
- 回帰後のソース46ファイルのSHA-256: `test_reports/p1_completion_sources_20260906.json`。対象には制御基盤、7ラッパーと呼出元シーン、関連設定、テストを含む。修正コミット後の作業ツリーと照合し、不一致0件を確認した。
- 最新の依存確認: `test_reports/kids_preflight_20260906_101821.json`。
- 資料の照合: 更新したMarkdown 10本のローカルリンク67件に欠落なし。報告の変更一覧55ファイルはGit差分と一致し、`git diff --check`も成功。別タスクの未追跡ファイルは含めていない。

これらのローカル証跡はGit無視対象。Gitには変更・検証結果・人間の確認手順を残す。テスト数だけで範囲を判断せず、下表の実行経路と失敗条件を確認した。

## ゴール要件との照合

|要件|現在の実装・検証根拠|候補準備としての判定／実機で残ること|
|---|---|---|
|P1 #2：明示した本番入口だけを起動|`manager.py` の `load_config` → `resolve_production_scenes` → カメラ生成。省略・null・空・重複・対象外・path逸脱・欠落・不正profile/sourceを拒否。JSON入口からの失敗と明示順序は `tests/test_production_playlist.py`、source/profileは `tests/test_runtime_validation.py`|実装・検証済み。専用configは `finger_colorfull_dots_acer.py` の1本だけ。7本の候補一覧を本番採用と扱わない|
|P1 #6：途中取得・例外・解放失敗時の所有|Managerと7シーンが取得済み資源を登録し、解放失敗後も独立したcleanupを実行。カメラhelperは `VideoCapture` が返った直後に所有登録し、release成功時だけ参照解除。`test_cleanup`、`test_scene_resources`、`test_camera_reconnect` が初期化途中・多重失敗・停止競合を実行|実装・検証済み。ネイティブopen/read/releaseが戻らない場合の強制回復は保証しない。実機の終了・再取得は別途評価|
|P1 #9：物理カメラとprofileの一致|Managerが環境変数→JSON→内部既定を解決し、設定元と実値を記録。Relayが物理カメラを所有し、子へ解決値と共有接続を渡す。`test_camera_profile` が環境優先、Acer profileの上書き防止、機器名矛盾、共有必須時の物理fallback禁止を検証|実装・検証済み。会場での露出・ズーム・画角と保存値はMac UIで実映像を見て判断|
|P1 #1：受信準備を確認するhandshake|`scene_control.py`、runner、ManagerがREADY→START→START_ACK→FIRST_FRAMEを処理。ID/PID/共有カメラ・正のframe_idを照合し、成功前に旧シーンを終了しない。実TCPと実fixture子プロセスで遅延・例外・接続断・ID不一致・分割JSON・切替反復を検証|実装・検証済み。通知は処理と描画API呼出し完了。実パネルの表示品質・座標の目視合格を代用しない|
|P1 #3：失敗後の再取得とフレーム更新|失敗capを解放するまで同じ所有者は新規openしない。解放成功後に再取得し、共有メモリ名を維持。停止後のbackend再試行を禁止。空・古い・不完全フレームを拒否。実共有メモリ／スレッド＋疑似captureで再取得失敗→復帰、停止中、release失敗→復帰を検証|実装・検証済み。実USBの抜去・再接続、番号変化、ドライバー停止はHuman Check Required|
|映像と操作座標の構造的一致|基準シーンが `prepare_camera_frame` の同じmirror/layoutを表示とMediaPipe入力・指先投影へ使用。四隅・中央・異なる縦横比と1px境界、退出後・古い映像の除去を実ソース／数値試験で確認|構造と自動検証は完了。Acer／Xiaomiで5点を人間が確認し、子供の体感を評価|
|プロセス・ハンドル・記録|Windows Jobで中継Pythonと実子を管理。実OS上のfixtureで親終了後の子回収、Job close、無関係PID拒否。容量制限付きログ、frame・PID・CPU・メモリ・handleの観測と終了理由を記録|基礎と試験手段は実装・検証済み。実GPU資源・温度・長時間の増加傾向は未合格|
|起動・保留・rollback・確認順|[起動手順](KIDS_TEST_START.md)、[Mac UI](OPERATOR_PANEL.md)、[基礎・耐久計画](ENDURANCE_TEST_PLAN.md)、[全変更と保留](PRODUCTION_CANDIDATE_REPORT_20260906.md)を現行CLIと照合。READMEの旧入口を履歴と明示|必要な手順を用意。ネットワーク方式・実機表示先・見た目の判断は人間へ渡す|
|Gitと合格表現|main/stableへの統合・force push・本番昇格を行わず、各修正を候補ブランチへ通常push。metadataは実機/目視を自動合格にせず、実機結果を時点別に記録|候補準備の完了と現場での合格を区別する|

## 独立レビュー：Standards

`c9cc221` の基盤と7シーンの差分を確認したレビューでは、規約への確定違反は0件。非必須の命名上の指摘は1件：`_scan_and_shuffle_scenes` は現在、明示リストを解決するだけだが旧名を保持している。ユーザーの最小変更方針に従い、機能を妨げない命名変更は見送った。これは仕様欠落や実機障害と同じ扱いにはしない。

## 独立レビュー：Spec

初回レビューで次の2件を再現した。どちらも修正後の独立mock確認で解消を確認し、全回帰94件も通過した。

|所見|修正前の証拠|最小変更と再検証|コミット|
|---|---|---|---|
|P1 #2：一覧省略時に7本へ補完|JSON `{}` とcamera値だけのJSONで、設定エラーになる前にカメラ生成へ進む。新しい入口試験の2 subtestが失敗|内部の7本defaultを削除し、一覧未指定を既存の起動前検証で拒否。省略/null/空の4ケースは終了コード2、カメラ/SceneManager生成0回。明示した2本の順序は維持|`40db032`|
|P1 #6/#3：初期設定とreleaseが両方失敗するとcapを失う|helperから戻る前に例外が出るためRelayの代入が行われず、2回の再取得でopenも2回。新規2試験で保持失敗を確認|helperで取得直後に所有登録し、release成功時だけ解除。独立mockで失敗中は再取得2回でもopen1回、解放成功後だけ次のopenへ進む。初回/再取得/単独起動/停止中/各native操作の失敗を含む8テストを追加|`d94ba5d`|

採用範囲の不当な拡大や、修正後の限定確認で新たな確定的不具合は見つからなかった。レビューは全条件の数学的証明や、未接続の機材での成功を意味しない。

## 実機証拠の時点を分ける

以前の実C922n試験では、初回露出戻りの補正後に基準シーンを **30.719秒無中断、起動時29.69fps、その後約30fps、exit0、当該PID残留なし** と確認した。証跡は `test_reports/kids_trial_20260906_093003_197744800/`。そのmetadataは当時の `45c1d29 + dirty` を記録し、対応する変更は後に `c9cc221` へコミットした。

今回のplaylist・二重失敗所有の追加修正後は、94件のカメラなし回帰と依存確認まで。以前の30秒結果を今回の実機再検証として数えない。別作業のTouchDesigner／Bridgeと競合するカメラ起動は行っていない。別タスクの動的HTMLや関連サーバーにも変更を加えていない。

ユーザーから動的HTMLのサイドタスク完了を受領。3ファイルは別成果物として保持する。旧lean-ctxスキル表示は要再確認との報告を残し、MCP・フック解除済みという状態と区別する。P1修正のためにツール設定を変更する必要は生じていない。

## 人間が次に確認する順序

1. 使用する映像用Pythonを指定して `Start Kids Test.cmd --check`。カメラを使う別作業は保存・通常終了し、C922nの所有を解放してから候補を起動する。
2. 最初は `finger_colorfull_dots_acer.py` の1シーン。大人が中央と四隅、退出・再入場を確認し、次に子供・複数人の反応位置と分かりやすさを見る。
3. Macの接続方式を選び、選んだ接続のAcer側IPv4で操作UIを開く。露出・ズームを適用→読戻しと映像→JSON保存→再起動後確認。接続方式と共通透過率の対象は回答待ちであり、通信・透過率実装を完了扱いしない。
4. 30分の単一シーン、20回切替、実USB復帰、終了後の再取得を別々に行う。無中断と途中再起動を混同せず、失敗時はログ・PID・機材条件を保存する。
5. Xiaomi接続後は表示先・Windowsのメイン画面・解像度・DPIを確認する。現在の子供向け設定は `DISPLAY_TARGET=primary` なので、TVへ出たことを推測せず、対象画面で5点座標を再確認する。
6. 続くソフトウェア経路の確認順は `finger_grid_interaction_acer.py` → `particle_storm_acer.py`。目視選定・本番採用とは別。基礎合格を記録した後に12時間試験へ進む。

Mac接続の確認はユーザーが準備できる時点で他の実機項目と並行できる。権限の未解決保留は現在なし。PB-01は解除済みの履歴であり、未再現の単発テスト失敗を権限不足と決めつけない。

## ロールバック

ManagerをUIの終了操作、Manager Controlのq、またはコンソールCtrl+Cで通常終了する。今回の追加2件だけを比較する基点は `c9cc221`。共有履歴を消さず、必要に応じて `d94ba5d`、`40db032` の順にrevertする。未保存の別作業を含む作業ツリーで一括reset/cleanを行わない。

カメラ値は変更前の値をUIで適用・確認・保存して戻す。JSONをnullにするだけで機器の状態が戻るとは限らない。Managerと子は同じ候補版を使い、HARUCAM2の新旧を混在させない。
