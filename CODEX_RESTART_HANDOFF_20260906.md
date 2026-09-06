# Codex再起動用引継ぎ — Rebirth 2026 Acer本線

更新時刻: 2026-09-06 Grid実機試験終了後

## 安全基準とGit

- 作業ブランチ: `codex/rebirth2026-production-candidate`
- 長期の安全基準点: `705b081`
- grid入口のpush済みcommit: `9bfd1c4`。再開時はリモート先端を読み直す。
- main/stableへの統合、force push、本番昇格は行わない。
- 再開時は最初に `git status --short --branch` と `git log -3 --oneline --decorate` を読み、推測で状態を補わない。
- 無関係な未追跡物 `20260906-current-status.html`、`TD_BUSINESS_RESEARCH_20260906.md`、`status_dashboard/` は変更・stageしない。

## 現在の実機構成

- Acer Windows 11一台で実行・制御・映像出力を完結する。
- C922n USB cameraをManagerが所有し、sceneは共有メモリ経由で読む。
- DISPLAY1は操作管理用。XiaomiはHDMI拡張画面DISPLAY5で、観客映像をfullscreen表示する。
- Mac、Bluetooth PAN、Macとのネットワーク接続は本番構成から外し、追加調査しない。
- 部屋の照明を点灯した条件。OS再起動後のC922n実値は露出-5、zoom 100。Dots比較試験では露出-4、zoom 176を実行中だけ一時適用し、JSONへ保存していない。

## 完了済みのDots試験

- OS再起動後、再起動前のPython PIDが0であることを確認して新規起動した。
- scene: `finger_colorfull_dots_acer.py` → `finger_colorfull_dots_2.py`
- trial: `test_reports/kids_trial_20260906_204802_629994100`
- 起動時のC922n診断: 1280×720、30fps、MJPG、実測30.01fps。
- OS再起動でカメラ実値は露出-5／zoom 100へ戻った。比較用にAPIで露出-4／zoom 176を一時適用し、JSONには保存していない。
- `duration_reached`、exit 0、`trial_elapsed=1800.672s`で30分試験を完走。camera read failure 0、reopen 0、last errorなし、最大frame gap 0.079秒。
- 179件のSceneMetricsはfps最小23.36、中央値27.46、最大35.2。
- 暖機後のscene working setはfirst 228,442,112、last 241,893,376、min 225,132,544、max 241,893,376 bytes。handlesはfirst 660、last 655、min 653、max 660。
- Manager working setはfirst 164,925,440、last 159,178,752、min 158,830,592、max 164,925,440 bytes。handlesはfirst 895、last 887、min 886、max 895。
- 終了後は対象PID、対象窓、共有メモリの残留なし。
- scene終了時にMediaPipe `wait_until_idle` の`KeyboardInterrupt`、runner側に`ERROR notification failed: ConnectionAbortedError`が記録された。運転中のカメラ失敗ではなく終了コードと資源解放は正常だが、完全無エラーとは記録しない。
- operator URLの認証tokenは資料へ書かない。

## 人間が確認済みの範囲

照明あり・露出-4・zoom 176の条件で、ユーザーが次をそれぞれ `ok` と回答した。

1. 中央で白い円が指先に追従し、近傍のdotsが波打つ。
2. 左上、右上、左下、右下で大きな座標ずれや左右反転がない。
3. 手を画面外へ出すと白い円が消え、自律波が続き、手を戻すと白い円が再出現する。
4. 両手を同時に映すと、左右の人差し指それぞれに白い円が出て、両方の近傍で波が起きる。

これは成人一人による基本確認である。子供、二人同時、暗所、USB抜き差し、gridへの切替後の残留、12時間、本番採用は未確認。

## 完了済みのGrid試験

- commit `9bfd1c4`で`--scene grid`入口をリモートへpush済み。実機preflightも成功した。
- trial: `test_reports/kids_trial_20260906_212343_63088200`
- C922n診断: 1280×720、30fps、MJPG、実測29.97fps。
- 露出-4／zoom 176を一時適用し、JSONには保存していない。
- ユーザーが、中央の座標一致と網を引く操作、pinch時の赤markerと線の切断、退出時のmarker消失と約8秒以内の修復、両手で別々に網を引く操作をすべて`ok`と確認した。
- `operator_quit`、exit 0、`trial_elapsed=1772.672s`（約29分32.672秒）。30分に届いていないため30分完走とはしない。
- camera read failure 0、reopen 0、last errorなし、最大frame gap 0.094秒。終了後は対象PID、対象窓、共有メモリの残留なし。
- 終了ログに`cv2.flip`中の`KeyboardInterrupt`と`Runner ERROR notification failed: ConnectionAbortedError`があり、完全無エラーとは記録しない。
- 子供、2人同時、暗所、正味30分、長時間、本番採用は未確認。

## 次の作業: particle_storm

1. Gitのbranch・HEAD・working treeを確認する。
2. particle_stormを既存のManager、shared camera、DISPLAY5の経路で安全に起動できる入口があるか確認し、必要なら入口を整備して自動試験とpreflightを通す。
3. 起動前に対象PID、カメラ所有、共有メモリを確認して二重起動を避ける。
4. 実カメラとXiaomi実表示で、座標・操作・退出復帰を一項目ずつ確認する。
5. 終了後に対象PID、窓、共有メモリの残留を確認する。本番playlist採用は実機確認と別に判断する。

## Gridの補足

- `finger_grid_interaction_2.py` はPygame/OpenCV/MediaPipeの同期推論で最大5手。WGPUと外部assetは使わない。
- 共通helperでmirrorとlayoutを背景・指先へ共通適用し、生映像は減光しない。
- 中央の網を指で引き、親指と人差し指のpinchで線を切る。通常マーカーは白輪＋水色、pinchは赤。切断後3秒で修復開始し、通常は最大約7.5秒で再接続する。
- QUIT/EscとExitStack cleanupはある。scene内の`q`は未対応。Managerからの終了を使う。
- 次の目視は、座標一致、引く＋pinch切断、退出時マーカー消失＋網の再生の順。人間操作は一度に一項目だけ依頼する。

## Spheresの現在判定

- `colorfull_dots_spheres_acer.py` は照明あり条件で成人の中央追従・四隅・退出再入場を合格し、MVP比較候補。
- 暗い入力では白い円が出ず、新規Handsによる保存46フレーム再生も0/46検出だった。照明だけを点灯すると白い円が復帰した。暗さ、姿勢、距離の寄与は分離していない。
- 約3時間20分の表示後、Managerのoperator quitはexit 0。所有PIDと共有メモリ残留なし。ただしscene outputに`KeyboardInterrupt`とrunner ERROR通知の`ConnectionAbortedError`があり、完全な無エラーとは記録しない。
- 過去にscene側の9終了後すぐ再出現し、3回目で消えた申告がある。今回のManager終了では再現しなかったため未解決の要確認事項として維持する。

## Particle Storm完了時点の最新状態

**23:17追記：Saturnのpinch操作もユーザーがOK。** つまんで粒子を引き、開くと球へ戻る。次は両手による球と輪の個別操作。526秒時点camera failure/reopen 0、30分試験は継続中。

**23:13追記：Saturn中央確認にユーザーがOK。** 生映像と球・輪、金色カーソルの指先追従、粒子の引き寄せを確認済み。次はpinchで粒子を引いて離した後の形の復帰を確認する。30分試験は継続中、256秒時点camera failure/reopen 0。下記23:09の中央確認待ちは解消した。

**23:09追記：Saturn実機確認を開始。** `3106a7c`で単独起動入口をpush済み、両Pythonで219件成功。trial `kids_trial_20260906_230857_470252900`、scene PID 2152、Manager PID 2596。30分自動終了指定で運転中。露出-4／zoom 176を一時適用、保存なし。FIRST_FRAME受信、初回camera failure/reopen 0。人間の中央追従・粒子表示は回答待ちであり合格扱いしない。再開前にプロセスと最新ログを確認し二重起動を避ける。詳細は [Saturn実機確認](SATURN_MVP_REVIEW_20260906.md)。

- commit `c258d6c`で背景planeの深度書込みを止め、中央の生映像が粒子を隠す問題を修正してpush済み。
- 成人が中央の粒子表示、開掌による反発、拳による吸引をOKと確認した。
- trial `test_reports/kids_trial_20260906_222052_316031000`は`trial_elapsed_s=1809.953`、exit 0。camera read failure 0、reopen 0、最終errorなし、終了後PID・共有メモリ残留なし。
- 終了時のrendercanvas `KeyboardInterrupt`とrunner通知`ConnectionAbortedError`が残るため、完全無エラーとは扱わない。
- 共通経路監査の結論は、追加共通化をMVP前に行わないこと。物理カメラ所有、共有接続、mirror、letterbox、背景と同じ座標投影は既に共通化済み。検出・gesture・合成・欠損時挙動は個別差が大きい。
- 次はSaturnを個別preflightと実機確認へ進める。Particle Stormの`depth_write=False`は横展開しない。子供、両手または2人、暗所、12時間はHuman Check Required。

## 関連資料

- `PARTICLE_STORM_MVP_REVIEW_20260906.md`
- `DOTS_MVP_REVIEW_20260906.md`
- `GRID_MVP_REVIEW_20260906.md`
- `SPHERES_MVP_REVIEW_20260906.md`
- `SPHERES_RETRIAL_86590ee_20260906.md`
- `PRODUCTION_CANDIDATE_PROGRESS.md`
- `KIDS_TEST_START.md`
- `ENDURANCE_TEST_PLAN.md`
