# Colorful Dots Spheres：高密度の発光と斜め回転

2026-09-06。対象は実ファイル `colorfull_dots_spheres.py`。ユーザーの「粒子を増やし、滑らかでリッチな画に」「回転軸を斜めへ」という追加指示を反映した候補。作業ブランチは `codex/rebirth2026-production-candidate`、安全基準点 `705b081`、直前の2画面入口は `9e0c1c4`。球体候補`01c8076`は通常push済みで、15:57:43からXiaomiで実表示した。

**16:10台までの実機更新:** 初回フレームへ到達し、ユーザーから「斜め回転に見える」と回答があった。確認済みなのは回転軸の見え方だけで、手の座標・複数人・子供・30分などの合格ではない。背景形式変換と高分解能時計の追加修正`18016ab`も通常pushし、同じManagerのローカルUIから再読み込みした。手なしの短時間で描画50.32～50.84fpsを記録したが、60fps合格とはしない。下記の約59fpsは別の合成計測値である。

## 描画と操作

- 8層は維持し、1層300点から1,200点へ、合計2,400点から9,600点へ増量。
- 画面内で約45度、奥行き方向にも傾いた軸の回転。各層に小さな軸・速度差と緩やかな変化を持たせる。
- 1,500フレームごとの角度リセットと全面フラッシュを廃止。単調時計による経過秒から姿勢を計算し、フレーム数で速度が変わらない。
- 硬い円から、中心光と柔らかい発光を持つ固定スプライトへ変更。背面は弱く光らせて奥行きを出す。回転計算はNumPyでまとめ、加算描画でZソートを省く。
- ランダムな震えを、指先近傍から広がる連続した波と局所発光へ変更。最大6本の手の検出は既存値を維持。検出順が変わっても近い手を優先対応し、未検出・古いフレームでは操作点を消す。
- カメラ認識は単一ワーカー、描画は60fpsを目標とする独立ループ。最新1フレームを受け渡し、0.5秒で失効。物理カメラはManagerが所有し、sceneは共有カメラ必須。
- 映像と指先は共通のmirror/letterbox変換を使う。認識だけを伸縮させない。FIRST_FRAMEは実カメラ画像の処理と画面への提示後に限る。
- ワーカーの停止待ちは最大2秒。戻らないnative呼出しは例外を残し、所有thread以外からカメラを解放しない。描画例外がある場合は元例外を保持して、解放失敗をnoteへ追加する。

実装箇所は `spheres_visuals.py`、`spheres_camera.py`、`colorfull_dots_spheres.py`。新しいラッパーは `colorfull_dots_spheres_acer.py`。

## 起動

既存の映像用Pythonを `KIDZDISCO_PYTHON` に指定した状態で、次の順に実行する。

```bat
"Start Rebirth Acer.cmd" --scene spheres --check
"Start Rebirth Acer.cmd" --scene spheres
```

`configs/rebirth_spheres_acer_xiaomi.json` で球体ラッパー1本だけを選ぶ。`--scene`未指定は従来のdots。Acerを操作画面、Xiaomiを観客画面とする配置・C922n設定は同じ。`--scene spheres`は`--audience`を伴う入口でのみ使用する。元sceneの直接起動は共有カメラ必須のため対象外。TCPハンドシェイクを持つ共通ランナーへ統一した。

## 01c8076までの検証

- Python 3.11：199件／12.649秒、OK・終了コード0。
- 既存映像venv Python 3.12.10：199件／12.478秒、OK・終了コード0。
- 追加試験：球体の分布・斜め軸・連続性・手の対応16件、cameraワーカー20件、sceneの提示順・例外解放9件、入口5件。増員時の手の取り違えと、既報エラーをcleanupで置換する問題は赤から緑へ確認。
- 15:53:10 JSTの実機preflightは成功。DISPLAY1=(0,0,1920,1080)、Xiaomi DISPLAY5=(1920,0,1920,1080)。この確認はカメラを開かない。
- 実NumPyの投影でも9,600点・有限値・画面内・有効sprite範囲を確認。50秒境界の最大移動は約0.0018px。中央の指による0.5px超の移動は2,247点、遠方400px超の最大影響は約0.006px。6本重複時も各軸32px以内に制限。
- 1080pのカメラなしCPU描画計測：旧描画平均4.68ms、新描画9.46ms、6本の仮想指あり10.55ms／p95 14.83ms。点数増による負荷増はある。カメラ・推論・presentを含まない値で、実画面60fpsの合格ではない。
- 発光スプライトは初期化時の2,880枚で固定。フレームごとに光用Surfaceを追加しない。実演の見え方はHuman Check Required。

ローカル証拠（Git対象外）は `test_reports/spheres_unittest_py311_20260906.txt`、`spheres_unittest_py312_20260906.txt`、`spheres_render_benchmark_20260906.json`、`spheres_numeric_check_20260906.json`、`kids_preflight_20260906_155310.json`。数値検査の43,200秒は時刻を入力した計算だけで、12時間耐久ではない。

## 同時に完了した時間処理の修正

`particle_storm_2.py` と `saturn_particles_2.py` の物理更新を単一の `monotonic()` 差分に変更。ParticleのMediaPipe VIDEO時刻は同じmsでも増加させる。修正前は時計逆行・同msで2エラー、両sceneの物理経過で4 subtest失敗。追加6件と既存の初回描画2件・資源5件は成功。Saturnの既存timestampガードと演出用時計は今回の対象外。これらGPU sceneは現在の球体playlistへ追加していない。

## 実機と保留

`01c8076`で15:57:43に実起動し、試験IDは`test_reports/kids_trial_20260906_155744_219024000`。FIRST_FRAMEは`detail.elapsed_s=1.953`、frame_id 53、実シーンPID 31428、wrapper PID 13992、Manager PID 31968。画面観測（SKY）でXiaomi上のウィンドウは1920×1080、原点(1920,0)だった。15:58:11の`[SpheresMetrics]`はrender 34.3fps、camera_update 15.9fps、描画9,600点。取得失敗は0で、16:07:11のManager sampleもread_failures 0／reopen_attempts 0だった。描画ループとシーン内の画像更新の指標であり、パネルの実表示FPSや物理USBカメラの取得FPSとは分ける。

ユーザーの「斜め回転に見える」は回転軸の見え方の確認として記録する。光量・滑らかさの最終承認、手への追従・中央と四隅の座標一致、複数人、子供の理解、単一30分・切替反復・USB復帰・12時間はHuman Check Required。既存dotsの継続表示を球体の合格へ流用しない。

旧dotsの継続表示`kids_trial_20260906_152123_937833500`は15:57:22にローカルUIから`operator_quit`で終了し、`run_end.exit_code=0`、`trial_elapsed_s=2151.406`（約35分51秒）、`completed_switches=0`だった。時間経過と正常終了の記録は得られたが、操作位置の一致は未確認であり、単一30分の総合合格とはしない。新旧試験の終了後資源もそれぞれで照合する。

16:09:02の追加照合で旧dotsのManager 15164は終了コード0、実シーン34932は0xC000013Aで終了済み、作成時刻も記録と一致した。wrapper 35320は不在。起動補助の旧PID 24500は別プロセスに再利用されていたため、現在の同番号の終了コードを旧試験に付けない。旧SHM `harukaze_cam_15164_dba3257436cf`は読取attachがWinError 2となり不在を確認した。これをspheresや全GPU資源の終了後確認へ流用しない。

## 背景合成の切り分けと追加修正（18016ab）

同一9,600点のカメラなし合成で、24bit RGB背景への透過合成に大きな時間を使うことを確認した。`test_reports/spheres_alpha_probe_20260906.json`は`camera_opened=false`、`physical_display_opened=false`の計測である。

| 背景の形式 | 平均背景合成 | 平均粒子描画 | 合成ループ |
|---|---|---|---|
| RGB24のまま | 17.33ms | 9.50ms | 37.24fps |
| display形式へconvert | 3.00ms | 9.32ms | 59.21fps |

convert自体の平均約2.32msも含む比較で、粒子数は減らしていない。これは合成経路の差を示す限定診断であり、カメラ・認識・Xiaomi実表示を含む59fps成功ではない。mainへ背景の最小限のconvertと、動きの時刻更新を高分解能`perf_counter()`にする修正を加え、`18016ab`として通常pushした。

修正後の全回帰はPython 3.11で199件／12.839秒、映像3.12.10で199件／12.915秒、両方OK・exit0。`test_reports/spheres_main_probe_20260906.json`では実mainを本物のSDLと合成snapshotで通し、35.95→57.08fps、背景cornerのRGBAは前後とも`[25,17,12,255]`で一致、Feedとpygameの解放成功を確認した。こちらもカメラ・物理画面は開いていないため、実機値とは分ける。

16:09:18のローカルUI Nextで同じspheresを再読み込みした。根拠は`test_reports/spheres_reload_20260906.json`と同一trialの制御ログ。新しい実シーンPIDは21644、wrapperは21108で、Manager 31968とSHM `harukaze_cam_31968_dd1fd99cc3ee`を維持した。16:09:20のFIRST_FRAMEは`detail.elapsed_s=2.421`、frame_id 20698。

同じ16:09:20に旧sphere 31428／13992へ`scene_switch`の停止要求が出て、約0.2秒後に`scene_output_end`を記録した。旧出力にはKeyboardInterruptと`Runner ERROR notification failed: ConnectionAbortedError`のnoteがある。閉鎖済みcontrolへの終了時通知で観測されたnoteとして保持し、「すべてエラーなし」とはしない。新sceneは継続し、switch_errorはなかった。追加のSKY観測では対象の球体1窓（id 8260830）とManager Control 1窓（id 1117412）を確認した。出力終了や窓数だけで全OS／GPU資源の解放を断定しない。

16:09:28～16:10:08の`[SpheresMetrics]`はrender 50.32～50.84fps、camera_updateは最初の19.17fpsを経て暖機後22.07～22.87fps、9,600点、hands 0。16:10:12のsample（elapsed 748.062秒）はread_failures 0、reopen_attempts 0、last_error null、switch_count 1、promotion_count 2、switch_error nullだった。手が映っていない条件での短時間改善であり、実機60fps・手の操作・複数人・30分合格とはしない。

16:20:09～16:20:29には`hands=1`のsampleを3回観測し、renderは50.55～50.77fps、camera_updateは16.88～20.09fpsだった。16:20:34時点でも取得失敗・再接続試行は0、switch_errorはnull。実カメラから手が検出された記録であり、指付近の波や発光が見えるか、映像と指先の位置が一致するかという確認依頼への回答はまだない。

Bluetooth PANとMac–Acer接続検証は完全中止のまま。ネットワーク設定・購入・本番昇格は行わない。復帰はdots入口 `Start Rebirth Acer.cmd`、コードは候補commit単位のrevert、全体基準は `705b081`。main/stableの強制変更は行わない。
