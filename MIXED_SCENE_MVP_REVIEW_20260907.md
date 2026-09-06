# 異種シーン切替と観客表示のMVP確認

## 05:47現在：タスクバーNGの修正後、Stormの再確認待ち

最初のSpheres→Storm切替後、ユーザーはタスクバー残留を報告。表示合格にはしない。GLFW配置順が最後の枠除去でclientをずらすことを非表示の実ウィンドウでも再現し、`096bace` で順序だけ修正、回帰と実シーン再測定を実施した。詳細は `TASKBAR_MVP_FIX_20260907.md`。

同じManager内でエージェントがStorm→Spheres→Stormを実行し、新Storm10920/wrapper27308、FIRST_FRAME05:46:28、switch3/promotion4。Manager6788/SHM/露出-4/zoom176を維持、camera failure/reopen0。旧/中継シーンのPID稼働なし。05:46:48の新Storm領域はXiaomi全面と一致し、下端3点はタスクバーでなくStorm。これは人間の目視合格の代わりではない。

次はAcer側CodexをクリックしてからStorm中央に開掌を映し、タスクバーが出ず中央で反発が続くか一まとまりだけ確認して待つ。現trialは05:49:49頃の上限で終了する。追加方針として全シーンの機能切替の光/色通知とビジュアルガイドをMVP後の重要要件へ記録した（`POST_MVP_INTERACTION_GUIDANCE.md`）。

## 05:20現在：起動完了、最初の手動切替結果待ち

- Spheres先行試験は05:19:07 duration_reached/exit0/1800.625秒/1promotion。途中再起動なし、対象4 PID稼働なし・SHM不在を確認。終了時例外はSPHERES_MVP_REVIEWに別記して保留。
- 準備済みCLI/一時設定で起動し、trial `test_reports/mixed_visual_20260907_051941_163497/trial`。Manager6788、初回Spheres実PID27560/wrapper27320、外側10936、SHM `harukaze_cam_6788_e199384fb591`。FIRST_FRAMEは05:19:49、launch経過1.859秒。30分上限は05:49:49頃で自動切替なし。
- ローカル操作APIが応答し、露出-4/zoom176を実値で確認、camera_error null。Codex右側にこの試験専用操作ページを開いた。まだNextを実行していない。
- 人間への確認は「次のシーンへ」を一度だけ押し、Stormに切り替わって中央の開いた手へ粒子が反発し、古い球体/管理窓/タスクバーが残らないか。人間の回答前に合否を決めない。現在のSpheres単一表示を異種切替成功とは数えない。
- 診断は `test_reports/inspect_mixed_visual_20260907.py`。一時JSON/ローカルhelperのみで製品コード・既存configs・OS変更なし。単一試験を途中で切り替えず、終了/解放後に別試験を起動した。

以下は05:10時点の準備記録。

## 今回確認する範囲

- Acer Windows 11のみ、DISPLAY1操作、Xiaomi HDMI拡張DISPLAY5観客表示、C922nをManagerが一つだけ所有する。
- `colorfull_dots_spheres_acer.py`（実体 `colorfull_dots_spheres.py`、Pygame）→ `particle_storm_acer.py`（実体 `particle_storm_2.py`、WGPU/GLFW）の手動切替から始める。両者の成人基礎確認済みの良さを変えず、異なる描画方式間の起動/終了・表示・共有カメラ継続を確認するため。この2種類を本番採用確定したものではない。
- Spheres単体ではAcer側Codexをクリックしてもタスクバー露出・最小化なしとユーザーOK。Stormで報告されたXiaomi下端のタスクバー露出はMVP mustのまま。切替後や別描画方式へ合格を流用しない。
- Storm左右各240pxの操作不能帯は別の既知課題。今回の切替後の手の反応は中央で見る。左右帯の解決や画面全域の位置一致を合格にしない。

## 先行試験を保護する

`kids_trial_20260907_044858_631260000` のSpheres単一30分は05:19頃終了予定。途中でNext/USB抜去/プロセス終了を混ぜない。今の単一シーン用UIでNextを押すとSpheresを再起動するため、切替用構成を起動するまでは人間へNext操作を求めない。

準備した `test_reports/analyze_spheres_final_20260907.py` はrun_endとPID/SHMを読む。完了前はrun_end/post_exitをnullで残す。GPUメモリと目視を自動合格にはしない。

## 既存の入口と試験専用設定

- `manager.py --config <試験専用JSON> --report-dir <新規フォルダー> --operator-host 127.0.0.1 --operator-port 8766 --duration-seconds 1800`。既存CLIを使用し、自動切替のオプションは付けない。30分上限は放置防止で、この混在試験を単一30分合格とは数えない。
- 一時JSON `test_reports/mixed_visual_profile_20260907.json` は既存Spheres設定を土台に `PRODUCTION_SCENES` を上の2項目の順に限定。PRELOAD_COUNT=0、TRANSITION_ENABLED=false、CLAP_MONITOR_ENABLED=false、SHARED_CAMERA_ENABLED=true。露出-4/zoom176はこれまでの実機条件を維持するための試験値。元のconfigs配下は変更していない。
- 描画Pythonは既存3.12.10のvenv。RENDERCANVAS_BACKEND=glfw、既存AUDIENCE_DPI_ENVを起動環境に設定。
- `prepare_mixed_visual_20260907.py` で既存load_config/resolve_production_scenes/check_runtimeと画面解決を実行し成功。両実体の構文、MediaPipe/Pygame/WGPU/GLFW依存、手モデルファイル存在、2画面配置を確認。物理カメラ・描画はこのpreflightでは未確認。
- `start_mixed_visual_20260907.py` は先行run_endのduration_reached/exit0/1800秒以上/1promotion、残留Manager/acer子プロセスとSHM不在を確認してから新規起動する。自動的な終了・残留除去は行わない。ローカル操作トークンはローカルstdoutだけに保持し、資料へ転記しない。

## 人間へ提示する最初の一まとまり

切替用試験のSpheresがFIRST_FRAMEまで起動し、専用操作ページの接続を確認してから、Acer側「次のシーンへ」を一度だけ押す。XiaomiでStormへ替わり、古い球体/管理窓/タスクバーが残らず、中央に映した開いた手に粒子が反発するかを30秒程度見る。失敗時は重ねてNextを押さず結果を受け取り、同時刻ログと照合する。まだこの操作を依頼していない。

その一回の合否後に、逆方向、操作側フォーカス、反復を必要な分だけ分けて提示する。手動一回を20回反復・無人自動・USB復帰・12時間合格の代わりにしない。

## 記録とロールバック

現時点の変更は文書と無視対象test_reports内の試験準備のみ。製品コード・本番保存設定・OSを変更していない。次試験の停止はその試験の操作UI「Managerを終了」を使い、残留を確認して既存の単一シーン入口へ戻す。main/stableは変更せず、安全基準点705b081を維持する。
