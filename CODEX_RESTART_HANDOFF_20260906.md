## 2026-09-07 06:15 最新：異種20回完走、USB復帰の人間確認待ち

Spheres/Stormの20秒間隔20回試験は06:14:04に switch_count_reached / exit0 / trial_elapsed471.078秒 / completed_switches20 / promotions21で終了。trialは `test_reports/mixed_repeat20_20260907_060604_788024/trial`、解析は同runのsummary.json。21件のFIRST_FRAME、旧シーン停止20件すべて新FIRST_FRAMEより後。同じManager17972/SHMを維持、camera read failure/reopen0、最大frame gap0.079秒、定常sampleは3 PID。一時重複sample最大5 PID。記録41プロセス世代は全て終了、SHM不在。別のCIM確認でもManager/scene入口の稼働なし。例外を含む出力52レコードはすべて該当シーンへの停止要求以後であり、終了時例外の保留として残す。GPUメモリ未取得、20回すべての人間目視・12時間耐久は未確認。

次の独立試験としてSpheresを既存入口で15分上限起動。run `spheres_usb_20260907_061446_031927`、trial `kids_trial_20260907_061447_164283500`。Manager23956/scene21332/wrapper17244/外側26752、SHM `harukaze_cam_23956_c4b44e01e3cf`。FIRST_FRAME1.765秒、C922n1280x720@30MJPG実測30.00。露出-4/zoom176を一時適用して実値一致、JSON保存なし。まだUSBは抜き差ししていない。次はC922nだけを抜いて5秒後に同じUSBへ戻し、30秒以内の生映像と中央の指反応復帰を人間に確認して待つ。他の設定や照明は変えない。再起動/残留/設定再反映はログ照合し、未回答で合格にしない。約06:29:55に上限終了。

今回の変更は検証記録のみ。ロールバック先は製品変更のない直前cce7d52、GLFW修正を含む製品基準096bace、従来安全基準705b081を維持。main/stable変更なし。

## 2026-09-07 06:06 最新状態

SaturnのGLFW修正後のタスクバー非表示と中央追従はユーザー `ok` で確認済み。通常終了・PID/SHM解放済み。現在は `mixed_repeat20_20260907_060604_788024/trial` でSpheres/Stormの20回自動切替を実施中。まだ完走扱いにしない。試験中はNextやUSB抜差しを混ぜない。終了ログと残留を確認してから、次のC922n物理再接続確認を一まとまりだけ提示して人間を待つ。製品変更なし。詳細はMIXED_SCENE_MVP_REVIEWとSATURN_MVP_REVIEW参照。

# Codex再起動用引継ぎ — Rebirth 2026 Acer本線

追加記憶（2026-09-07）：ユーザーがParticle Stormの時間経過で画面内の粒子が疎らになる点を指摘。画面外へ出た辺りの粒子を中心から再発生させる案を、後の演出調整用としてPOST_MVP_INTERACTION_GUIDANCE.mdへ保存。現在は実装せず、タスクバー修正後の目視確認を優先する。この追加要望はタスクバー再確認への合格回答ではない。

更新時刻: 2026-09-07 05:57 逆方向切替OK・Saturn表示修正影響の確認待ち

05:57最優先：Storm→Spheresの逆方向切替、白い円/指反応、旧Storm/タスクバー非残留をユーザーOK。trial055116は05:55:28 operator_quit/exit0/switch2/promotion3、対象PID稼働なし・SHM不在で終了。現在はSaturnへの共通GLFW配置修正の影響だけ結果待ち。trial `kids_trial_20260907_055537_173816900`、run `saturn_reentry_20260907_055535_820485`、Manager19580/scene23484/wrapper10480/外側19508、露出-4/zoom176一時適用、FIRST_FRAME3.781秒、06:11頃に15分上限終了。新しい操作ページを右側に開いた。Acer側Codexクリック→中央で人差し指を動かし、Xiaomi下端にタスクバーなし・金色カーソルと近くの粒子が追従するか一まとまりだけ提示し待つ。実測でSaturn全面一致/下端3点Saturnだが人間の合格にはしない。再開時 `test_reports/inspect_saturn_mvp_20260906.py`（applyなし）で現状確認。以下は履歴。

05:52最優先：ユーザーがStorm修正後「タスクバーが出ず、粒子が手から押し広げられる」と明示確認。先行混在trial051941は05:49:50 duration_reached/exit0/switch3/promotion4で終了し、稼働PID/SHM残留なし。次の逆方向確認用trialは `test_reports/mixed_visual_20260907_055116_887043/trial`。Manager25012/外側17516、表示Storm実PID27308/wrapper3636、SHM `harukaze_cam_25012_3b24e0835c6e`。エージェントが最初のSpheres→StormをAPIで一度切替済み（switch1/promotion2）。人間には右側の新操作パネルでNext一回→Spheresの白い円/指の反応・旧Storm/タスクバー残留なしの一まとまりだけ提示して待つ。06:21:25頃に上限終了。旧PID27308は旧wrapper、新27308は新StormへのPID再利用。露出-4/zoom176、camera failure/reopen0。Storm左右帯、他GLFWの表示、20回反復/USB/子供等は保留。以下は履歴。

05:47最優先：ユーザーは最初の異種切替後「タスクバーが残る」と回答。GLFWの位置/サイズ指定後の枠除去で領域がずれることを実測し、配置順だけ `096bace` で修正・push。新Storm10920/wrapper27308（FIRST_FRAME05:46:28、4.250秒）を同じManager6788/SHMで表示中。trial混在051941はswitch3/promotion4、旧Storm/中継Spheres稼働なし、camera failure/reopen0、露出-4/zoom176。新Stormは実測でXiaomi全面一致・下端3点がStorm。次はAcer側Codexをクリック後、中央の開掌反発とタスクバー非露出を人間へ一まとまりで依頼して結果を待つ。まだ目視合格にしない。05:49:49頃自動終了予定なので続行時は現ログを確認。修正/回帰/一度のHTTP試験10053と再実行成功はTASKBAR_MVP_FIX_20260907.md。ユーザー追加要望「全シーンの機能切替を光/色で分かりやすく、各機能のビジュアルガイドはMVP後重要」はPOST_MVP_INTERACTION_GUIDANCE.mdに保存。MVP検証を止めず、今はガイド実装をしない。以下は履歴。

05:20最優先：Spheres単一30分は05:19:07 duration_reached/exit0/1800.625秒/1promotion、途中再起動なし。対象4 PID稼働なし・SHM不在。終了時KeyboardInterrupt/通知ConnectionAbortedErrorは保留。次の2種類手動切替用trialを起動済み：`test_reports/mixed_visual_20260907_051941_163497/trial`、Manager6788/Spheres27560/wrapper27320/外側10936、SHM `harukaze_cam_6788_e199384fb591`。FIRST_FRAME1.859秒、露出-4/zoom176読戻しOK。05:49:49頃の30分上限、自動切替なし。新しい操作ページをCodex右側で開いた。現在はSpheres表示中で、ユーザーに「次のシーンへ」一回→XiaomiのStorm中央で開掌反発・古い窓/タスクバー残留なしだけを提示し、結果を待つ。こちらからNextは未送信。旧単一シーン用URLを使わせない。再開時は `test_reports/inspect_mixed_visual_20260907.py` で現状を読む。Storm左右帯方針・タスクバーMVP must・2人/子供/USB/12時間は保留。以下は履歴。

05:10最優先：Acer側Codex入力欄のクリック後も、XiaomiのSpheresはタスクバー露出/最小化なしとユーザーOK。StormのタスクバーMVP mustは未解決。Spheres単一30分を途中で切らず、trial044858の05:19頃自動終了とPID/SHM不在を先に確認する。解析 `test_reports/analyze_spheres_final_20260907.py`、その後用の手動切替起動 `test_reports/start_mixed_visual_20260907.py` を準備。起動ガードは先行試験のduration_reached/exit0/1800秒/1promotion、既存Manager等不在、SHM不在。準備済み試験専用JSONはSpheres→Stormの2項目のみ、先読み/拍手/遷移/自動切替なし、露出-4/zoom176、本番JSON未変更。新試験開始後は人間へ「次のシーンへ」一回の確認だけ提示して待つ。既存単一シーンUIのNextは同じSpheresを再起動するので、現試験中に押させない。詳細はMIXED_SCENE_MVP_REVIEW_20260907.md。以下は履歴。

05:02最優先：Spheresの成人両手同時反応はユーザーOK。次は同じ表示のままAcer側Codexをクリックし、Xiaomiのタスクバー露出/最小化の有無だけを確認して結果を待つ。まだこの操作の合格回答はない。trial `kids_trial_20260907_044858_631260000` は05:01:57時点778.969秒、promotion1、camera failure/reopen0。30分と終了後残留は未判定、05:19頃終了予定。Spheresの結果でStormのタスクバーMVP mustや異種切替後の表示を代用しない。Storm左右帯方針も保留。製品コード/設定変更なし。以下は過去の再開位置。

04:49最優先：Grid四隅ユーザーOK、30分同一scene/再起動なし、対象PID/SHM残留なし。終了例外は保留。現在はSpheresの両手だけ結果待ち。trial `kids_trial_20260907_044858_631260000`、Manager20416/scene26992/wrapper1604/外側11588、露出-4/zoom176一時適用、30分上限（05:19頃）。中央/四隅/退出復帰の既存OKは再要求しない。Storm左右帯方針とタスクバーMVP mustは未解決。一まとまりずつ結果を待つ。以下は過去の再開位置。

04:11最優先：Stormの成人両手をユーザーOK、旧trial040343はoperator_quit/exit0・PID/SHM残留なしで終了。現在はGridの四隅だけ結果待ち。trial `kids_trial_20260907_041040_336399400`、Manager16228/scene21940/wrapper26728/外側27252、露出-4/zoom176一時適用、30分上限（04:41頃）。Gridは正味30分も不足しているため目視後も継続予定。中央/pinch/退出/両手の既存OKは再確認不要。Storm左右帯の方針とタスクバーMVP mustは未解決。以下の旧結果待ちは履歴。

04:05最新：ユーザーが実施後に `ok` と回答し、Storm退出再入場を合格として記録。次は同trial040343（15分上限、04:19頃自動終了）で両手を離して片手開掌/片手拳、左右を入れ替え同時反応を確認し結果待ち。両手・2人同時は未確認。左右操作不能帯は方針未確定、タスクバー露出はMVP must。以下は履歴。

04:04最新：ユーザー「準備ok」は合格でなく準備完了。前trial034658は04:02:08に15分自動終了、対象プロセス/SHM残留なし。現trial `kids_trial_20260907_040343_885724400` を同条件で再表示（Manager2404/scene17432/wrapper20300/外側27288、15分上限）。退出10秒→中央再入場のみ結果待ち。左右帯/タスクバーMVP mustは未解決。以下の旧PIDと予定時刻は履歴。

## 最優先の再開位置（タスクバー指摘後）

- 最新ユーザー指示：観客画面下端のWindowsタスクバー露出はMVP must。今すぐ修正でなくてよいので次へ進む。工程3の表示/操作UI/切替確認で修正と再確認を必須にする。原因・対応は未確認。
- 左右操作不能帯の対応方針は未確定だが、それを理由に全体を止めず、Storm退出10秒→中央再入場の1まとまりのみ再提示し結果待ち。同trialは03:58時点で生存、04:02頃に15分自動終了。続きで消えていたら最新ログとPIDを確認する。

- ユーザーが左右端に映像/手が入らない点を指摘。現コードの1280×720→640×480→中央1440×1080配置で左右各240pxが操作範囲外になることを合成入力と実関数で確認。四隅OKは生映像内の一致に限定し、画面全域は未合格。
- 左右の帯をなくして全画面操作にする案は検出640×360への最小調整。まだ製品コード変更なし・採用未確定。退出再入場の中央操作確認は最新指示で再開する。

- Spider修正後の目視をユーザーがOK。単一30分再起動なし、目視後の対象PID/SHM残留なし。終了時例外は解消済みとはしない。
- Particle Stormの四隅一致をユーザーがOK。現在は退出10秒・再入場の動作だけを提示して結果待ち。trial `kids_trial_20260907_034658_174238400`、15分上限、Manager24104/scene25540/wrapper27160/外側2436。FIRST_FRAME3.672秒、露出-4/zoom176一時適用、保存なし。
- 退出再入場・両手は未確認。中央操作・30分は再確認不要。次項目へ進む前にユーザーの結果を待つ。再開時は最新ログ/プロセスを読み、二重起動しない。詳細は `PARTICLE_STORM_MVP_REVIEW_20260906.md` 冒頭。
- 以下の古い「次の作業」「確認待ち」は履歴。現在のネットワーク/本番構成や保留項目は最新の指示・上記を優先する。

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

**23:32追記：Saturnの四隅の位置一致をユーザーがOK。** 次は手を画面から外した際のカーソル消失、自律回転と形の復帰、再入場での追従復帰を確認する。1397秒時点camera failure/reopen 0、scene/Manager生存、30分試験継続中。

**23:29追記：Saturnの両手操作をユーザーがOK。** 金色で球、水色で輪が別々に反応する。次は四隅の指先とカーソル位置の一致を確認する。1197秒時点camera failure/reopen 0、30分試験は継続中。2人同時・子供は未確認。

**23:17追記：Saturnのpinch操作もユーザーがOK。** つまんで粒子を引き、開くと球へ戻る。次は両手による球と輪の個別操作。526秒時点camera failure/reopen 0、30分試験は継続中。

**23:13追記：Saturn中央確認にユーザーがOK。** 生映像と球・輪、金色カーソルの指先追従、粒子の引き寄せを確認済み。次はpinchで粒子を引いて離した後の形の復帰を確認する。30分試験は継続中、256秒時点camera failure/reopen 0。下記23:09の中央確認待ちは解消した。

**23:09追記：Saturn実機確認を開始。** `3106a7c`で単独起動入口をpush済み、両Pythonで219件成功。trial `kids_trial_20260906_230857_470252900`、scene PID 2152、Manager PID 2596。30分自動終了指定で運転中。露出-4／zoom 176を一時適用、保存なし。FIRST_FRAME受信、初回camera failure/reopen 0。人間の中央追従・粒子表示は回答待ちであり合格扱いしない。再開前にプロセスと最新ログを確認し二重起動を避ける。詳細は [Saturn実機確認](SATURN_MVP_REVIEW_20260906.md)。

- commit `c258d6c`で背景planeの深度書込みを止め、中央の生映像が粒子を隠す問題を修正してpush済み。
- 成人が中央の粒子表示、開掌による反発、拳による吸引をOKと確認した。
- trial `test_reports/kids_trial_20260906_222052_316031000`は`trial_elapsed_s=1809.953`、exit 0。camera read failure 0、reopen 0、最終errorなし、終了後PID・共有メモリ残留なし。
- 終了時のrendercanvas `KeyboardInterrupt`とrunner通知`ConnectionAbortedError`が残るため、完全無エラーとは扱わない。
- 共通経路監査の結論は、追加共通化をMVP前に行わないこと。物理カメラ所有、共有接続、mirror、letterbox、背景と同じ座標投影は既に共通化済み。検出・gesture・合成・欠損時挙動は個別差が大きい。
- 次はSaturnを個別preflightと実機確認へ進める。Particle Stormの`depth_write=False`は横展開しない。子供、両手または2人、暗所、12時間はHuman Check Required。

## 2026-09-07 Saturn最新状態

- 退出10秒→再入場の目視確認をユーザーがOK。中央、pinch、成人の両手、四隅に続き基本確認が完了。詳細は `SATURN_MVP_REVIEW_20260906.md` 冒頭。
- 前回30分はduration_reached・exit 0、1800.719秒。旧PID/共有メモリ残留なし。瞬間的なウィンドウ表示の原因は未特定であり、推測修正なし。
- 15分の再試験 `kids_trial_20260907_014844_739981500` を起動済み。再開時には生存・最新ログを確認し二重起動を避ける。起動後226秒時点の取得失敗/再接続0。再試験終了後の残留、Manager切り替え反復、子供・2人同時・現場条件・12時間は未確認。

## 関連資料

2026-09-07 03:42最新：Spider修正後trial030519は単一30分/再起動0・camera failure/reopen0、対象PID/SHM残留なし。終了時KeyboardInterrupt/ConnectionAbortedErrorは保留。工程1の修正後目視用にtrial `kids_trial_20260907_034242_304284400` を10分上限で起動（Manager19836/scene21332/wrapper23448/外側19572）。露出-4/zoom176一時適用。人間の約1分の結果待ち。最新指示は未確認だけ一まとまりを提示し回答を待つこと。次シーンを先行起動しない。

2026-09-07 02:19更新：Spiderの中央、両手独立、四隅、退出再入場を成人ユーザーがOK。片手の右下100px第2目標も確認し維持。ただし現trialで02:06:08/02:08:19/02:13:10の3回scene_exit（code0、理由null）と再起動を検出。操作の有無は確認待ち。連続30分合格としない。最新camera failure/reopen0、描画35fps。詳細はSPIDER_MVP_REVIEW_20260907.md冒頭。

2026-09-07 02:02更新：Saturn退出再入場OKを記録後、operator_quitで終了（exit0、766.516秒）。対象PID/共有メモリ残留なし。次のSpider単独入口を `1dfca5e` でpushし、`kids_trial_20260907_020159_984874500` を30分上限で起動。中央の目視確認待ち。露出-4/zoom176は一時適用。詳細 `SPIDER_MVP_REVIEW_20260907.md`。再開時は現PID/ログを確認し二重起動を避ける。

- `PARTICLE_STORM_MVP_REVIEW_20260906.md`
- `DOTS_MVP_REVIEW_20260906.md`
- `GRID_MVP_REVIEW_20260906.md`
- `SPHERES_MVP_REVIEW_20260906.md`
- `SPHERES_RETRIAL_86590ee_20260906.md`
- `PRODUCTION_CANDIDATE_PROGRESS.md`
- `KIDS_TEST_START.md`
- `ENDURANCE_TEST_PLAN.md`
