# Acer単体・Xiaomi出力への本線再開

2026-09-06。安全基準点は`705b081`、作業ブランチは`codex/rebirth2026-production-candidate`。dotsのXiaomi実表示試験は`9e0c1c4`、15:57台からのspheresは`01c8076`で実施し、16:09台に追加修正`18016ab`を再読み込みした。いずれも通常push済みで、main/stableへ統合していない。

**16:10台までの更新:** dotsの2分試験は時間到達で、約35分51秒の継続表示はローカルUIから正常終了した。spheresの初回表示と「斜め回転に見える」という回答を確認し、追加修正後は同じManager／SHMを保った再読み込みで描画50.32～50.84fpsを記録した。手が映らない短時間の値であり、60fps、手の追従・5点一致・複数人・子供・30分の総合合格とは分ける。

## 最新の運用方針

ユーザー指示でBluetooth PANとMac–Acerネットワーク検証を完全中止した。以後、調査・設定変更・接続検証を行わない。Macは本番構成から外し、Acer Windows 11の1台で実行・制御・映像出力を完結させる。

操作管理はAcerの主画面、観客映像はHDMI接続のXiaomi拡張画面の全領域を使う。画面の役割とWindows内部の番号を混同しない。

## 機材の照合

| 項目 | 根拠と確認範囲 |
|---|---|
| Acer | 「rebirth2026 Sol 再開」の過去ユーザー発言ではNitro AN515-58、i7-12650H、RAM16GB、RTX 4060 Laptop 8GB＋Intel UHD。過去申告と実機再測定は別。 |
| カメラ | 本線で実取得に使用してきたC922n、Windows名`c922 Pro Stream Webcam`を維持。 |
| Xiaomi | 今回ユーザーがHDMI接続。WmiMonitorIDでメーカーXMD・名称Mi TVを読み取った。型番は今回の申告`L32M8-A2TWN`と旧発言`L32MB-A2TWN`に表記差があり、ラベル実読は未実施。 |
| 操作画面 | 実読`\\.\DISPLAY1`、primary、(0,0)、1920×1080。 |
| 観客画面 | 実読`\\.\DISPLAY5`、non-primary、(1920,0)、1920×1080。用途上の2枚目であって内部番号2ではない。 |
| 現在の出力モード | 15:10:17 JST、EnumDisplaySettingsでDISPLAY5の1920×1080・60Hz・32bit、接続GPUはRTX 4060 Laptopを確認。OS報告値でありパネル実測FPSではない。 |

機材発言の参照先は「rebirth2026 Sol 再開」(task `01a06293-b8d9-7832-b177-fcc674669de4`)のturn `01a0666f-48fa-7510-98ba-815935d07f22`、`01a0678f-92fb-7fb0-be52-e459baf8b16d`、`01a06795-94a2-7bf3-b61b-57e1466cf7c2`。旧1360×800は過去のシーン窓サイズとして扱い、Xiaomiの解像度へ継承しない。

## 実装した変更

- `scene_profile_runner.py`: 終了処理を個別に試行し、finish・control.close・signal・環境復元の一つが失敗しても残りを試す。元のシーン例外を保持し、追加失敗はexception noteへ残す。借用していたcontrol/lifecycleを復元し、借用controlは閉じない。
- `stage_display.py`・Manager・表示helper: 本番設定の2画面名とprimary状態、非重複の拡張領域をカメラ確保前に確認する。欠落・複製・不一致は終了コード2。古い固定座標や列挙順に依存せず、実測の座標・サイズを子と切替効果へ渡す。子の起動時に配置が変わっていた場合も拒否する。
- audience起動時はGUI初期化前にPer-monitor DPIを確認し、SDLの座標スケーリングを無効にする。これは物理ピクセルの座標系を揃える処理で、異なる表示倍率の実機目視に合格したことを意味しない。
- 新しい`Start Rebirth Acer.cmd`は`configs/rebirth_acer_xiaomi.json`を使用し、基準dotsの1シーンだけを起動する。旧`Start Kids Test.cmd`とprimary設定は机上確認用に保持する。
- 操作UIはaudienceモードで`127.0.0.1`に限定。Manager Controlは主画面の座標へ配置する。露出・ズーム・保存・Next・終了は既存のローカルUIを使う。カメラは引き続きManagerだけが所有する。
- preflightに実ロードモジュールの版・パスとSDL版を追加した。既存環境にpygame/pygame-ceのmetadataが共存しているため、metadataだけで実ロード版を断定しない。依存の更新・新環境への入替はしていない。

DPIの根拠は[Microsoftの設定API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext)、[SDLのDPI awareness](https://wiki.libsdl.org/SDL2/SDL_HINT_WINDOWS_DPI_AWARENESS)、[SDLの座標scaling](https://wiki.libsdl.org/SDL2/SDL_HINT_WINDOWS_DPI_SCALING)。既設定の場合のPer-monitor V1も許容し、厳密V2の保証とは記録しない。

## 9e0c1c4での基盤検証

- 保全していた終了処理の赤テストはSHA-256一致を確認して復帰。追加条件も含め修正前11件/18失敗から11件成功。
- 観客画面の不足・誤配置は修正前4件/5失敗で再現。追加した起動順・DPI・配置共有・ローカルUI条件を含む12件が成功。
- 全回帰: Python 3.11は143件/10.547秒、既存映像venv Python 3.12.10は143件/13.721秒。ともにOK・終了コード0。
- 新audience preflightは実機で成功。`test_reports/kids_preflight_20260906_150744.json`はカメラ/ウィンドウを開かない確認で、実映像と視覚確認のフラグはfalse。
- `git diff --check`成功。旧カメラ試験の20回交代・30分の証拠は今回の変更の実機合格へ移し替えない。

回帰の記録は`test_reports/windows_single_pc_unittest_py311_20260906.txt`と`windows_single_pc_unittest_py312_20260906.txt`。ローカル証拠はGit対象外。

## 9e0c1c4でのXiaomi短時間試験と継続表示

| 項目 | 2分試験 | 時間制限なしの表示 |
|---|---|---|
| 開始 | 15:17台、初回フレーム15:17:27 | 15:21台、初回フレーム15:21:31 |
| 試験ID | `kids_trial_20260906_151719_217295700` | `kids_trial_20260906_152123_937833500` |
| FIRST_FRAMEの記録値 | `detail.elapsed_s=1.719`、frame_id 47 | `detail.elapsed_s=1.453`、frame_id 42 |
| 終了・継続 | 初回フレーム後の試験開始から終了まで120.609秒。15:19:27に`duration_reached`・`exit_code=0`。正常交代0、昇格1 | `duration_seconds=null`で開始し、15:57:22にローカルUIから`operator_quit`。`exit_code=0`、`trial_elapsed_s=2151.406`（約35分51秒）。正常交代0、昇格1 |
| カメラの最終読取sample | read_failures 0、reopen_attempts 0、最大フレーム間隔約0.063秒 | 終了前15:57:15のsampleはread_failures 0、reopen_attempts 0、最大フレーム間隔約0.204秒 |

FIRST_FRAMEの上記秒数は`scene_control.detail.elapsed_s`で、Manager全体の経過時間とは別である。2分試験の`scene_output.jsonl`には共有カメラ接続とDISPLAY5の1920×1080・座標(1920,0)への配置が記録され、終了要求後に`runner_end`も記録された。配置ログと終了ログだけで、画面の見切れ・DPI・OS資源解放を合格にしない。

別担当が15:32:44 JSTに旧2分試験のcleanupを追加照合した。旧PID 7788／37664は不在。旧Manager 31312は終了コード0、旧シーン25232は終了コード3221225786（0xC000013A）で終了済みで、作成時刻も記録と一致した。終了済みprocess objectは照会できるため「全PID消失」とは記録しない。旧共有メモリ`harukaze_cam_31312_c68238653520`は読取attachがFileNotFoundError／WinError 2となり、存在しないことを確認した。当時継続表示中のManager 15164などは照合対象から除外し、操作・停止していない。その後のdots継続表示やspheresの終了後確認、すべてのGPU資源の解放へこの結果を広げない。

旧dots継続表示の終了後は、16:09:02に別担当が追加照合した。Manager 15164は終了コード0、実シーン34932は0xC000013Aで終了済みで、作成時刻も記録と一致。wrapper 35320は不在だった。旧起動補助PID 24500は別プロセスに再利用されており、現在の同番号の終了コードを旧起動補助の結果とは扱わない。旧共有メモリ`harukaze_cam_15164_dba3257436cf`は読取attachでWinError 2となり不在を確認した。終了済みprocess objectの照会可否と生存を区別し、spheresの終了後確認や全GPU資源の解放へは流用しない。

実ロード値は両試験のpreflightで一致した。numpy 2.2.6、cv2 4.12.0、pygame-ceの実module 2.5.7／SDL 2.32.10、mediapipe 0.10.14。パッケージmetadataのpygame 2.6.1やcv2 4.12.0.88と実ロードmoduleの版を混同しない。根拠は`test_reports/kids_preflight_20260906_151719.json`と`kids_preflight_20260906_152123.json`の`loaded_modules`。環境の入替・依存更新は行っていない。

起動記録は`test_reports/audience_active_trial_20260906.json`と`audience_continuous_session_20260906.json`、制御・描画記録は上記各試験ディレクトリの`runtime.jsonl`と`scene_output.jsonl`。dots継続表示は約35分51秒と正常終了を記録したが、操作位置の一致は未確認であり、単一30分の総合合格とはしない。終了後の資源も試験ごとに照合する。操作トークンやトークン付きURLは本文へ保存しない。

ユーザーは最初に「反応しない」と申告した。その後のスクリーンショットでは白い円一つを観測し、手の検出は少なくとも一度あったと判断した。ただし継続した追従・遅延・中央と四隅の5点一致は未確認。「手のひらを5秒映す」確認依頼への回答はまだなく、反応問題の解消とは記録しない。

## 01c8076でのspheres実表示と追加診断

増量・滑らかな描画・斜めの回転軸という追加依頼に対する候補を`01c8076`として通常pushした。`Start Rebirth Acer.cmd --scene spheres`は`configs/rebirth_spheres_acer_xiaomi.json`の球体1本を選択する。未指定のdots入口は維持している。この段階の全回帰はPython 3.11で199件／12.649秒、映像3.12.10で199件／12.478秒、両方OK・exit0。詳細は [球体更新記録](SPHERES_VISUAL_UPDATE_20260906.md) を参照。

15:57:43に新spheresを実起動した。試験IDは`test_reports/kids_trial_20260906_155744_219024000`。FIRST_FRAMEの`detail.elapsed_s=1.953`、frame_id 53、実シーンPID 31428、wrapper 13992、Manager 31968。画面観測（SKY）でXiaomi上のウィンドウ1920×1080・原点(1920,0)を確認した。ユーザー回答「斜め回転に見える」は軸の見え方だけの確認として扱い、手座標・複数人・子供・30分などの合格へ広げない。

変更前15:58:11の`[SpheresMetrics]`はrender 34.3fps、camera_update 15.9fpsで、取得失敗0。これらは描画ループとシーン内の画像更新の指標で、パネル表示FPSや物理USB取得FPSとは別である。同一9,600点・カメラなしの`test_reports/spheres_alpha_probe_20260906.json`では、RGB24背景の平均合成17.33ms／37.24fpsに対し、display形式へconvertした背景は3.00ms／59.21fpsだった。これは合成計測であり、実機59fpsの成功ではない。

mainの最小convertと、動きの時刻更新を高分解能`perf_counter()`にする追加修正は`18016ab`として通常pushした。全回帰はPython 3.11で199件／12.839秒、映像3.12.10で199件／12.915秒、両方OK・exit0。`test_reports/spheres_main_probe_20260906.json`は実main・本物SDL・合成snapshotで35.95→57.08fps、背景corner RGBAの前後一致、Feed／pygame解放成功を記録した。カメラ・物理画面なしの検査である。

16:09:18のローカルUI Nextで同じtrial内のspheresを再読み込みした（`test_reports/spheres_reload_20260906.json`）。実シーンPIDは21644、wrapperは21108となり、Manager 31968とSHM `harukaze_cam_31968_dd1fd99cc3ee`は同じ。16:09:28～16:10:08のrenderは50.32～50.84fps、camera_updateは暖機後22.07～22.87fps、9,600点、hands 0だった。16:10:12のsampleはread_failures 0／reopen_attempts 0／last_error null、switch_count 1／promotion_count 2／switch_error null。これは手なし条件の短時間改善で、60fps・操作一致・複数人・30分の合格ではない。

再読み込みのFIRST_FRAMEは16:09:20、`detail.elapsed_s=2.421`、frame_id 20698。同時刻に旧sphere 31428／13992へ`scene_switch`の停止要求、約0.2秒後に`scene_output_end`を記録した。旧出力にはKeyboardInterruptと`Runner ERROR notification failed: ConnectionAbortedError`のnoteがあり、閉鎖済みcontrolへの終了時通知として記録する。新sceneは継続しswitch_errorはないが、全エラーなしとはしない。SKYの追加観測では対象の球体窓1つ（id 8260830）とManager Control窓1つ（id 1117412）だった。出力・窓の確認と全OS／GPU資源解放の確認は区別する。

## 次の実機確認と保留

`fblits`による追加軽量化は実装と画素一致・両Python199件回帰まで確認済みで、現在のscene PID 21644にはまだ再読み込みしていない。現表示の操作確認を続け、次の切替／起動後にFIRST_FRAME・実FPS・取得失敗・旧子プロセス終了を確認する。詳細は [球体更新記録](SPHERES_VISUAL_UPDATE_20260906.md) を参照。

16:20:09～16:20:29の球体ログに`hands=1`が3回あり、render 50.55～50.77fpsだった。取得失敗0は継続しているが、実際に指付近の波・発光が見えるかという問いへの回答は未着で、位置一致や操作性の合格へは広げない。

dotsの2分・約35分51秒の終了記録と、spheresの初回表示・軸の見え方の回答は得られた。次は各候補の手への追従・中央と四隅の一致、Acer側の操作窓、実際の光量と滑らかさを人間が確認する。旧2分試験の終了後照合は上記の範囲で記録し、その後の各セッションの終了後確認とは分ける。この資料更新のための表示停止・再起動は行っていない。

Human Check Requiredは、Xiaomi上でのC922n実映像と指先の中央/四隅一致、DPI・見切れ、複数人・子供の操作、単一30分、Xiaomi構成の切替反復、実USB復帰、画面抜去時のOS挙動、長時間試験。12時間試験は開始していない。GPU2シーンの実配置と映像品質も未確認で、この1シーン入口の採用へ混ぜていない。

## 起動・終了・ロールバック

起動は[KIDS_TEST_START.md](KIDS_TEST_START.md)、ローカルUIは[OPERATOR_PANEL.md](OPERATOR_PANEL.md)、試験順は[ENDURANCE_TEST_PLAN.md](ENDURANCE_TEST_PLAN.md)。既存映像venvを`KIDZDISCO_PYTHON`に指定して`Start Rebirth Acer.cmd --check`、成功後に通常起動する。

停止は操作UIの「Managerを終了」、Manager Controlのq、または起動したコンソールのCtrl+C。映像側のEsc/qは同じシーンを再起動する可能性がある。

`705b081`は復帰基準として履歴上に保持する。候補変更を取り消す場合は今回のコミットを個別にrevertし、履歴の強制書換えはしない。PAN試験設定は中止前の最後の観測が共有On・省電力Offで、中止後は再読取も復元も行っていない。現在の復元指示としては扱わない。
