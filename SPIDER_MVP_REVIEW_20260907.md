# Spider MVP実機確認

- 起動入口 `scripts/start_kids_test.py --audience --scene spider` を追加。既存 `spider_cursor_acer.py` → `spider_cursor_2.py` を使用。描画・操作コードの変更なし。
- 共通の一時profileでManagerが物理カメラを所有。先読み・拍手・遷移を無効化し、Xiaomi DISPLAY5へ単独表示する。
- 両Pythonで回帰222件成功。初回の全体試験はHTTP応答中にWinError10053が1件発生し、再実行では成功した。原因未特定として保持し、安定性の合格根拠にしない。実preflight成功。
- commit `1dfca5e` をpush後、trial `kids_trial_20260907_020159_984874500` を開始。FIRST_FRAME 1.86秒。C922n 1280x720@30 MJPG、診断30.00fps。露出-4/zoom176一時適用、保存なし。30分上限。
- 直前のSaturn再試験はoperator_quit、exit0、766.516秒。対象4 PIDと共有メモリの残留なしを確認してから起動した。
- 人間確認は未実施。最初に生映像と蜘蛛の表示、中央の白い円と指先の位置一致、蜘蛛の追従を確認する。1本の手では水色の目標が白い目標から100pxずれる既存仕様。2本目の手、四隅、退出復帰、子供・2人同時、終了残留、切替反復、長時間は未確認。
