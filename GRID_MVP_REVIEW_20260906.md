# Finger Grid Interactionの成人基礎操作確認

## 2026-09-07 04:49：四隅OK・正味30分完了

- ユーザーが四隅付近で人差し指と白い輪/水色マーカーが重なる確認に `ok` と回答。成人の四隅一致を合格として記録。中央/pinch/退出/両手の既存合格は維持。
- trial `kids_trial_20260907_041040_336399400` は04:40:48にduration_reached、exit0、trial_elapsed1800.75秒、promotion_count1、途中scene_exitなし。同じsceneで正味30分の継続を確認。
- camera failure/reopen0、最大frame gap0.079秒。描画179サンプル17.25〜29.01fps、中央値26.9。暖機後scene working set226,426,880〜244,502,528 bytes、handles662〜669。Manager working set165,195,776〜171,692,032 bytes、handles915〜924。集計は同trial/grid_mvp_summary.json。
- 終了後の対象4 PIDと共有メモリ不在を確認。MediaPipe wait_until_idleのKeyboardInterruptとrunner ConnectionAbortedErrorは終了時に残るため完全無エラーとはしない。子供・2人同時・現場条件・12時間・異種切替は未確認。タスクバー露出のMVP必須対応は別管理。
- 次はSpheresの未確認の両手反応だけ。Gridの成人基礎項目を重ねて要求しない。以下の30分未合格は前回の履歴。

## 2026-09-07 04:11：四隅と正味30分の不足確認を開始

- 中央操作・pinch・退出修復・両手の既存OKは維持。専用の確認記録がない四隅のみをユーザーへ提示し、結果待ち。白い輪/水色マーカーが映った人差し指に四隅付近でも重なることを確認する。操作不能な帯など新たな指摘があれば別に記録し、画面全域の合格へ推測で広げない。
- 旧Particle StormのManager終了とPID/SHM不在を確認して、既存 `--audience --scene grid --duration-minutes 30` で起動。製品コード・永続設定の変更なし。
- trial `kids_trial_20260907_041040_336399400`。FIRST_FRAME1.359秒、C922n1280×720@30 MJPG診断29.99fps。露出-4/zoom176一時適用、保存なし。Manager16228/scene21940/wrapper26728/外側27252。約04:41に30分自動終了予定。
- 前回は29分32.672秒だったため、今回は四隅の短い目視確認後も同じsceneのまま30分ログを取る。現時点で30分完走・終了残留の合格にはしない。ユーザーに30分ずっと操作することは求めない。

2026-09-06。commit `9bfd1c4`でpush済みの`--scene grid`入口を使い、Acer Windows 11、C922n、Xiaomiの観客用拡張画面で実機確認した。trialは`test_reports/kids_trial_20260906_212343_63088200`。実機preflightは成功した。

**判定：露出-4／zoom 176の一時適用条件で、成人の中央操作、pinch切断、退出後の復帰、両手同時操作が合格。** 運転時間は1772.672秒（約29分32.672秒）で30分に届いていないため、30分完走とはしない。子供、2人同時、暗所、正味30分、長時間、本番採用は未確認である。

## 確認条件

| 項目 | 実際の確認条件 |
|---|---|
| trial | `test_reports/kids_trial_20260906_212343_63088200` |
| 入口 | commit `9bfd1c4`の`--scene grid`。リモートへpush済み |
| 入力 | C922n、1280×720・要求30fps・MJPG、実測29.97fps |
| 露出・ズーム | 露出-4／zoom 176を一時適用 |
| 永続化 | JSON保存なし。次回起動時の保存済み値として扱わない |

## 人間が確認した操作

| 項目 | 確認した動作 | 結果 |
|---|---|---|
| 中央・引く | 中央で座標が一致し、指で網を引ける | OK |
| pinch | pinch時にmarkerが赤くなり、線が切れる | OK |
| 退出・修復 | 退出するとmarkerが消え、網が約8秒以内に修復する | OK |
| 両手同時 | 両手で別々に網を引ける | OK |

両手同時は一人の成人による確認であり、2人同時、手の交差・遮蔽、子供の理解や操作性を確認した結果ではない。

## 運転と終了確認

`operator_quit`、exit 0、`trial_elapsed=1772.672s`で終了した。カメラは`read_failures=0`、`reopen_attempts=0`、`last_error=null`、`max_frame_gap=0.094s`。終了後は対象PID、対象窓、共有メモリの残留なしを確認した。

176件のSceneMetricsはfps最小14.98、中央値19.92、最大29.01だった。暖機後のscene working setはfirst 227,340,288 bytes、last 239,390,720 bytes、min 224,174,080 bytes、max 241,950,720 bytes、handlesはfirst 660、last 655、min 653、max 660。Manager working setはfirst 167,587,840 bytes、last 161,837,056 bytes、min 161,775,616 bytes、max 168,931,328 bytes、handlesはfirst 917、last 909、min 908、max 917だった。増え続けるhandle傾向は観測されなかった。fpsはDotsより低いため、操作合格とは分けて性能観測として残す。

ただし、終了ログには`cv2.flip`中の`KeyboardInterrupt`と`Runner ERROR notification failed: ConnectionAbortedError`がある。運転中のカメラ取得失敗ではなく、operator quit、終了コード、資源解放は正常だったが、完全無エラーとは記録しない。

## 残る確認

| 項目 | 状態 |
|---|---|
| 正味30分 | 未確認。今回の1772.672秒を30分へ丸めない |
| 子供 | 未確認。成人の結果から代用しない |
| 2人同時、手の交差・遮蔽 | 未確認。成人一人の両手同時はOK |
| 暗所 | 未確認 |
| 長時間 | 未確認 |
| 本番採用 | 未決定 |

次はparticle_stormの安全な起動入口を確認・整備してから、実カメラとXiaomi実表示で操作を確認する。トークン付きURLや一時認証値はこの資料へ記載しない。
