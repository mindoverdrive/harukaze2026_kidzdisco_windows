# Spider MVP実機確認

## 02:30 診断再試験

- ユーザーは不明なターミナルでCtrl+Cを押したと申告。旧ログの通常returnとは直接結び付けられず、原因確定にはしない。旧launcherは既にCREATE_NO_WINDOW/CREATE_NEW_PROCESS_GROUPを使用していた。
- `04fcdac`で既存notify_exit_requestを3つの終了経路（pygame_quit、escape_key、camera_read_failed）に追加。終了条件・映像・操作は変更せず、次回の理由判別のみを目的とする。Python3.11回帰222件成功。
- 旧試験はoperator_quitで停止、exit0、1674.515秒、promotion_count=5（初回以外4回）。共有メモリ不在。単一30分合格ではない。
- 新trial `kids_trial_20260907_023010_280243200`、30分上限。FIRST_FRAME1.547秒。露出-4/zoom176一時適用、保存なし。ユーザーにはターミナルでCtrl+C/Escを押さず通常の手操作で確認するよう依頼。原因・連続安定性は保留。

## 02:19 更新：成人の操作確認と再起動の保留

- ユーザーが中央の表示・追従、両手による2匹の独立操作、四隅の指位置一致、10秒退出後の円消失・映像継続・再入場時の追従再開をそれぞれOKと回答。
- 片手で2匹を操作できる挙動は維持する意向。中指の独立検出ではなく、人差し指から右下100pxの第2目標であることもユーザーが確認した。
- 最新1041.063秒時点camera failure/reopen 0、last_errorなし、最大frame gap 0.094秒、直近描画35fps、検出・描画エラーログなし。
- ただし02:06:08、02:08:19、02:13:10にscene_exitが発生。3回ともlauncher_exit_code=0、runner outcome=return、exit_request_reason=null。その後FIRST_FRAMEを再受信しpromotion_count=4。正常な連続30分運転とは扱わない。手動終了・カメラ読取終了などの原因は未特定で、ユーザー操作の有無を確認する。推測修正なし。
- 操作面のMVP候補として保持。終了・再起動の原因確認と単一30分、終了残留、Manager切替反復、子供・2人同時・長時間運転は保留。以下は起動時点の履歴。

- 起動入口 `scripts/start_kids_test.py --audience --scene spider` を追加。既存 `spider_cursor_acer.py` → `spider_cursor_2.py` を使用。描画・操作コードの変更なし。
- 共通の一時profileでManagerが物理カメラを所有。先読み・拍手・遷移を無効化し、Xiaomi DISPLAY5へ単独表示する。
- 両Pythonで回帰222件成功。初回の全体試験はHTTP応答中にWinError10053が1件発生し、再実行では成功した。原因未特定として保持し、安定性の合格根拠にしない。実preflight成功。
- commit `1dfca5e` をpush後、trial `kids_trial_20260907_020159_984874500` を開始。FIRST_FRAME 1.86秒。C922n 1280x720@30 MJPG、診断30.00fps。露出-4/zoom176一時適用、保存なし。30分上限。
- 直前のSaturn再試験はoperator_quit、exit0、766.516秒。対象4 PIDと共有メモリの残留なしを確認してから起動した。
- 人間確認は未実施。最初に生映像と蜘蛛の表示、中央の白い円と指先の位置一致、蜘蛛の追従を確認する。1本の手では水色の目標が白い目標から100pxずれる既存仕様。2本目の手、四隅、退出復帰、子供・2人同時、終了残留、切替反復、長時間は未確認。
