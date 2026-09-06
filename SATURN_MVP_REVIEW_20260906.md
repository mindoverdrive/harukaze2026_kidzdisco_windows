# Saturn実機確認

## 2026-09-07 更新：退出・再入場確認

- ユーザーが、両手を10秒外した後のカーソル消失・球とリングの回転継続・形の復帰、および片手を戻した際の追従再開に `ok` と回答。成人による今回の目視確認として合格。
- 前回試験は `kids_trial_20260906_230857_470252900`。23:39:06に `duration_reached`、終了コード0、`trial_elapsed_s=1800.719`。最終camera read failure/reopenは0。旧4 PIDと共有メモリの残留なしを再起動前に確認した。
- 「一瞬ウィンドウが見えた」という報告自体の発生源は未特定。前回試験のタイマー終了はログで確認できるが、この瞬間表示まで同じ原因と断定しない。
- 再試験 `kids_trial_20260907_014844_739981500` は15分上限。FIRST_FRAME 4.406秒、露出-4・zoom176を一時適用、JSON保存なし。226.594秒時点camera failure/reopen 0、switch_errorなし、直近描画26.76fps、検出・描画エラーなし。
- 判定：成人による基本操作を確認したMVP候補として次工程へ進める。子供・2人同時、現場距離と照明、Manager切り替え反復、12時間運転はHuman Check Requiredまたは未実施。前回30分の終了時例外ログ全体は未精査であり、完全無エラーとは記録しない。再試験の終了後残留はまだ未確認。


## 起動準備

`scripts/start_kids_test.py --audience --scene saturn` を追加。既存の単独試験profile生成とGPU依存検査を使用し、ManagerがC922nを所有、Xiaomi DISPLAY5へ出力する。scene実体の `saturn_particles_2.py` は変更していない。

- 通常Python: 全219件成功（12.089秒）
- 映像Python: 全219件成功（11.921秒）
- 実preflight: `kids_preflight_20260906_230738.json`、failuresなし。GLFW、モデル資産、DISPLAY1/5を確認。
- `pylinalg`の既存回転・逆回転APIはCPUで実行できた。

## 初回起動の観測（23:09）

- 起動入口のcommit `3106a7c`をpush後に起動した。
- trial: `test_reports/kids_trial_20260906_230857_470252900`
- 開始前のPythonプロセス0、旧Particle Storm共有メモリ残留なし。
- FIRST_FRAME受信: scene launch control開始から3.468秒。
- Manager PID 2596、scene PID 2152、wrapper PID 13320、外側launcher PID 23136。
- C922n診断: 1280×720・30fps・MJPG、実測30.01fps。
- 露出-4・zoom 176をAPIで一時適用し読戻し一致。JSON保存なし。
- 26.015秒時点: read failure 0、reopen 0、last_error null、最大frame gap 0.062秒。
- 最新SceneMetrics: processed_render_fps 30.0。初回の読取り範囲で描画・検出エラーログなし。
- 30分で自動終了する指定。現時点では運転中であり、30分試験・終了残留・全目視項目は未合格。

## 人間による目視確認

23:32更新：ユーザーが四隅の位置一致に`ok`と回答。生映像の左上・右上・左下・右下で、指先とカーソルが重なることを確認済み。退出・再入場は未確認。1397.968秒時点でcamera read failure 0、reopen 0、last_error null、最大frame gap 0.079秒。直近SceneMetrics 28.36fps、描画・検出エラーログなし。scene/Managerの生存も確認し、30分試験は継続中。

23:29更新：ユーザーが両手確認に`ok`と回答。金色カーソルで球、水色カーソルで輪へ別々に作用することを確認済み。成人一人の両手確認であり、2人同時・子供の確認には広げない。四隅、退出再入場は未確認。1197.703秒時点でcamera read failure 0、reopen 0、last_error null、最大frame gap 0.079秒。直近SceneMetrics 28.3fps、描画・検出エラーログなし。30分試験は継続中。

23:17更新：ユーザーがpinch確認に`ok`と回答。球の中央でつまんで横へ動かすと粒子を引け、指を開くと徐々に球へ戻ることを確認済み。2手、四隅、退出再入場は未確認。526.781秒時点でcamera read failure 0、reopen 0、last_error null、最大frame gap 0.079秒。直近SceneMetrics 26.86fps、描画・検出エラーログなし。30分試験は継続中。

23:13更新：ユーザーが最初の中央確認に`ok`と回答。生映像と球・輪の表示、金色カーソルの指先追従、近くの粒子の引き寄せを確認済みとする。pinch、2手、四隅、退出再入場は未確認。

同時点のログ：256.437秒、camera read failure 0、reopen 0、last_error null、最大frame gap 0.079秒。直近SceneMetrics 24.96fps、読み取った描画・検出エラーログなし。30分試験は継続中。

1. 生映像の上に球と輪が表示される。手首まで映し、人差し指を球の中央でゆっくり動かすと金色カーソルが指先に重なり、近くの球の粒子が追従する。
2. 親指と人差し指のpinchで球の粒子を引き、離すと形が戻る。カーソル色は手の役割色なのでpinch時も金色。
3. 2本目の手には水色カーソルが付き、輪へ作用する。検出順の交代による役割変更も観察する。
4. 四隅の位置一致と、退出・再入場の挙動を確認する。
5. 30分試験とManager切替反復、終了後の残留を確認する。

背景の単一3D scene構造と640×480入力は既存のまま。粒子遮蔽、縦横比、操作感はHuman Check Required。Particle Stormの目視結果を流用しない。
