# MacBook UIからの透過率調整：調査・実装計画

2026-09-06。状態：**透過対象は質問中・未確定。実装なし。** ソースの静的確認とAPI一次資料の調査のみを行った。全7シーンへの一括対応、Acer/C922n/Xiaomiでの透過表示、MacBookからの操作は未検証。

## ユーザーの最新要望

主担当から共有された発言を原文で記録する。

> 全体を通して常に、macで透過率をuiで、できればスライダーで調節できれば

共通スライダーで操作でき、シーン切替後も値を維持することが要望。対象が「シーン全体のウィンドウ」か「シーン内のカメラ背景」かは確認中であり、どちらも採用確定していない。UIの「透過率」と内部の不透明度は逆向きになるため、0%・100%で何が見えるかを確定してから表記する。

## 現在の接続点

7個の `*_acer.py` は同名の `_2.py` を共通ランナーで起動する。pygameは `finger_colorfull_dots`、`finger_mandala`、`finger_grid_interaction`、`fractal_moving`、`spider_cursor` の5本。`particle_storm` と `saturn_particles` はWGPU／pygfx／`rendercanvas.auto`。

全7本が `display_utils.prepare_camera_frame()` の返す **camera_frameをMediaPipe認識に、stage_frameを背景表示に使用**する。映像の配置と指の座標は同じlayoutを使う。物理C922nはManagerが所有し、子シーンは共有カメラに接続する構造を維持する。

| 解釈 | 最小の適用箇所・結果 | 注意点 |
|---|---|---|
| カメラ背景の濃さ | `display_utils.py` の `prepare_camera_frame()` でstage_frameだけを黒背景と合成。pygameの背景SurfaceとWGPUの背景textureへ共通に届く | 模様や粒子、認識入力は維持できる。下にあるTDなどの別ウィンドウは透けない |
| シーン全体の透明度 | Managerが所有するシーンのHWNDにWindowsの全体alphaを適用。初期値は共通のウィンドウ生成helperにも渡す | カメラ・模様・操作ガイドを含め全体が薄くなる。描画バックエンド別の対応と実際の合成結果は未確認 |

カメラ背景案では、**表示用の新しい配列にだけ処理する**。`fit_frame_to_size()` は原寸一致時に元配列を返すため、stage_frameのin-place変更は認識画像まで変えてしまう。カメラの露出・共有フレーム・MediaPipe入力・座標変換を透過率で変更しない。

## 共通値とライブ更新

`operator_panel.py` の認証済みAPIで表示設定を受け、Managerが最新値を保持する。カメラハンドルを触る露出／ズームのmailboxとは分ける。スライダーの連続操作は最新値にまとめ、適用状況をUIに戻し、JSON保存は確認済みの値に限定する案。新規起動・切替先・再起動時にも同じ共通値を引き継ぐ。

現在の `scene_control.py` は起動専用。ManagerはFIRST_FRAME後の昇格時に `_clear_preloaded()` からTCPを閉じ、子もSTART後は受信していない。カメラ背景案でこの通信を再利用する場合は、稼働中controlの保持、版番号付き表示設定、適用ACK、終了時の解放を追加する必要がある。既存7本の `notify_first_frame()` を共通受信の入口にできるが、カメラ取得失敗時も設定を受けられるようFIRST_FRAMEの成否条件とは分離する。

全体透過案はManager側からWindows APIを使う経路も選べる。`SceneLaunchControl.child_pid` はnonceとJob所属を検証した実interpreter PIDであり、`WindowsSceneJob.active_pids()` でも所有範囲を確認できる。`EnumWindows()` と `GetWindowThreadProcessId()` で照合し、**所有する対象シーンだけ**に適用する。タイトル一致やvenv launcher PIDだけで対象を決めず、Manager操作窓、TD、無関係なアプリを変更しない。終了したHWNDを保持し続けず、変更時にも所有を再確認する。[Windows列挙](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumwindows)、[ウィンドウのPID取得](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowthreadprocessid)

## 全体透過の制約と初回・切替時

Windowsの `SetLayeredWindowAttributes(..., LWA_ALPHA)` は0が完全透明、255が不透明。戻り値とエラーを確認し、失敗を適用済みと記録しない。既存styleを保存して復元できるようにする。[Microsoft API仕様](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setlayeredwindowattributes)

Microsoftは `CS_OWNDC`／`CS_CLASSDC` とlayered styleの併用を制限している。一方、GLFW 3.4は `CS_OWNDC` のウィンドウに公開opacity APIからlayered APIを使っている。この資料差だけでWGPUの対応可否を断定せず、実HWNDのstyle・API結果・画面を確認する。[Windows制約](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles)、[GLFW実装](https://github.com/glfw/glfw/blob/3.4/src/win32_window.c)

pygameには `Window.from_display_module().opacity` があるが `_sdl2` は実験的API。GLFWには `set_window_opacity()` があるがメインスレッドで呼び、framebuffer transparencyと併用しない。`rendercanvas.auto` の実バックエンドは未確定で、現在のfullscreen helperはGLFWの `_window` を想定している。[pygame公式](https://www.pygame.org/docs/ref/sdl2_video.html)、[GLFW API仕様](https://www.glfw.org/docs/latest/group__window.html)

初回・切替先のウィンドウ生成後にManagerが適用するだけでは、一瞬100%で表示される可能性がある。`setup_pygame_fullscreen()`／`setup_rendercanvas_fullscreen()` の生成直後に初期値を反映し、表示開始時に最新値へ一致させる案を検証する。新旧シーンが同時に見える間は旧シーンまで重なって合成される点も目視する。TDとの同時運転・GPU負荷・カメラ所有調整は、この透過機能だけでは解決しない。

## 最小確認と取得する証拠

1. 自動検証：0・50・100%、範囲外／NaN／型不正、連打、通信断、適用ACK、切替中の値変更と継承。カメラ案では原寸・拡大・余白付きの各ケースで認識画像とlayoutが不変であること。
2. Acer短時間確認：まずfinger dots、次にpygame別シーンとWGPU各1本。スライダー往復で認識・指先座標・演出が維持され、不透明状態へ戻せること。初回と切替時の不透明フラッシュ、残像、黒画面を目視する。
3. MacBook/PAN確認：同じUIから連続操作、再接続、切替後の値表示・実表示を照合。全体透過案では無関係なウィンドウ不変更と対象HWNDの終了も確認する。
4. 証拠：要求値／適用値／設定版番号、scene名／launch_id／launcher・interpreter PID、必要時HWND・style・Windowsエラー、切替時刻、描画FPS、終了結果。映像や人物画像は自動保存しない。API成功と人間の目視確認を分け、未確認はHuman Check Requiredとして残す。

この計画の作成ではコード・設定・カメラ・ウィンドウを変更していない。
