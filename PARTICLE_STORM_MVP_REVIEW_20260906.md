# Particle Storm MVP確認と共通経路監査

## 2026-09-07 03:47：残る四隅確認を開始

- 中央の描画・開掌反発・拳吸引・30分の既存結果は保持。資料に専用の合格記録がない四隅、退出再入場、両手を未確認として順に扱う。
- まず四隅の指先とカーソルの一致だけを提示し、ユーザー結果待ち。手首まで入れた開掌を映像内の左上→右上→右下→左下にゆっくり移動。水色カーソルが映った人差し指先に重なればOK。端に近づくほどずれる、反転、検出が途切れる場合はNGとして場所と症状を記録する。
- 起動コードの追加変更なし。trial `kids_trial_20260907_034658_174238400`、FIRST_FRAME3.672秒。露出-4/zoom176一時適用、保存なし。15分で自動終了。
- 旧Spider終了後のPID/共有メモリ不在を確認して起動。これはManagerを一度終了した別試験であり、同じManager内の異種シーン切替反復合格ではない。

## 判定

`particle_storm_acer.py` は、成人による基本操作と30分単一シーン試験を通過したMVP候補とする。子供、2人同時、暗所、12時間、本番採用は未確認であり、Human Check Requiredのまま残す。

中央の生映像が粒子を隠していた原因は、背景planeが深度を書き込み、後段のparticle sceneが同じdepth bufferを使っていたことだった。背景の色は維持したまま `MeshBasicMaterial(..., depth_write=False)` とし、背景が粒子を遮らないようにした。修正はcommit `c258d6c` で候補ブランチへpush済み。

## 実機結果

- 構成: Acer Windows 11、C922n、Xiaomi拡張画面 `DISPLAY5`
- trial: `test_reports/kids_trial_20260906_222052_316031000`
- C922n診断: 1280×720、30fps、MJPG、実測29.99fps
- 比較時設定: 露出-4、zoom 176を一時適用。JSONへは保存していない。
- `FIRST_FRAME`: scene開始要求から約3.55秒、Manager開始から3.781秒
- 人間確認: 生映像の上に中央の粒子が見える、開いた手で粒子が押し広げられる、拳で赤いカーソルになり粒子が引き寄せられる、の3点をOKと確認した。
- 連続試験: `operator_quit`、exit 0、`trial_elapsed_s=1809.953`。30分を超えた。
- カメラ: read failure 0、reopen 0、`last_error=null`、最大frame gap 0.109秒
- SceneMetrics 180件: 19.24～30.00fps、中央値25.96fps
- warm-up後のscene working set: 610,750,464 → 575,913,984 bytes、範囲562,233,344～625,815,552 bytes
- warm-up後のscene handles: 1214 → 1211、範囲1209～1214
- warm-up後のManager working set: 190,021,632 → 184,188,928 bytes
- warm-up後のManager handles: 925 → 918、範囲917～925
- 終了後: 対象PIDとManager所有共有メモリの残留なし
- 終了ログ: rendercanvas描画callback中の`KeyboardInterrupt`と`Runner ERROR notification failed: ConnectionAbortedError`がある。運転中障害ではなく終了要求時の記録だが、完全無エラーとは扱わない。

## 共通経路の監査

本番候補のAcerラッパーと実体、root直下のPython、Manager、Scene Runner、Shared Camera、Spheres専用workerを横断確認した。

既に次の最小共通経路が成立している。

1. `manager.py`の`SharedCameraRelay`が物理カメラを一元所有する。
2. Managerが共有メモリ情報を子シーンへ環境変数で渡す。
3. 各本番候補が`display_utils.open_camera()`から共有カメラへ接続する。
4. `prepare_camera_frame()`が左右反転、アスペクト比維持、余白付きstage画像を同じlayoutから作る。
5. `normalized_to_stage()`が、表示背景と同じlayoutでMediaPipeの正規化座標を画面座標へ変換する。

Dots、Grid、Mandala、Fractal、Particle Storm、Saturn、Spiderはこの経路を使う。Spheresも専用worker内で同じframe preparationと座標変換を使う。

## 共通化候補と今回の判断

追加候補は次のとおりだが、MVP前には実装しない。

- Pygame群に重複するBGR→RGB→Surface変換
- MediaPipe SolutionsとTasksの結果adapter
- カメラ読取失敗時の背景消去、前frame保持、scene終了の扱い
- Pygame、pygfx、Spheresの背景透過率制御
- Particle StormとSaturnに重複する画面座標から3D world座標への変換

理由は、重複行数より作品固有差の方が大きいためである。最大手数、検出閾値、pinch・拳・開掌の意味、2D／3D投影、Pygame透過canvas、pygfxのdepth、Spheresの加算合成、カメラ欠損時の継続方針が異なる。共通化すると合格済みシーンを含む再検証が必要になり、MVP完成を遅らせる。

Particle StormとSaturnはscene側で640×480を指定する。`CameraResizingProxy`が共有1280×720を640×480へ変換し、背景と検出座標は同じ変換を通るため位置は一致する。一方、元映像の縦横比が変わる可能性がある。Particle Stormは現在の正常基準を維持し、Saturn実機試験で横伸びや余白を目視してから個別判断する。

未採用の旧シーンには、独自mirror、resize、座標式、直接`VideoCapture`が残るものがある。候補に選ばれた時点で、既存共通経路へ最小限合わせてから実機試験する。

## 残る確認と次工程

Particle Stormには次を残す。

- 2人または両手で二つのカーソルと反応が独立すること
- 子供が開掌と拳の因果関係を理解できること
- 会場照明と距離で検出が途切れないこと
- 12時間連続試験
- 終了時のrendercanvas割り込み例外の扱い

残りのシーンは共通化作業を挟まず、既存経路を維持してpreflight、中央と四隅の座標、操作、退出再入場、複数人、30分、終了残留の順に個別確認する。次はParticle Stormと同じ依存環境を使うSaturnを優先するが、背景を同じ3D scene内へ置く構造はParticle Stormと異なるため、深度設定を横展開しない。
