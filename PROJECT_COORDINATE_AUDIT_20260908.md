# 座標・入力比率・投影監査

## ユーザー採用判断（監査後の確定）

ユーザーが「Particle Stormは、ああいうものとして良しとする」と指定。数値上の差は事実として残すが、現在の3D反応位置を意図した表現として採用し、修正対象から除外する。以下の修正候補記載はこの判断前の監査経過。Particle Stormは変更しない。

Saturn追加修正の実機確認にユーザーが「ok」と回答。その後の横断監査。今回は他シーンの製品コードを変更していない。

## 確定した問題

1. **Particle Storm / particle_storm_2.py:318**：Saturnと同じ縦FOV解釈が残る。実pygfx行列で指座標(1727,108)に対応する3D位置を再投影すると(2025.278,-60)。画面中心から約1.389倍に広がる。映像とカーソルは別のOrthographicCameraで描画しているため、カーソルが合っても粒子へ力を加える位置はずれる。最小修正はhalf_heightへ2/(1+aspect)を適用すること。合格済み操作感への影響があるため今回未変更。
2. **旧minecraft.py:410、hell_of_flies.py:368**：同じpygfx＋縦FOVとしての逆投影式。現本番リストには含まれない。移植前に実投影テストが必要。

Saturnは同じ検証で(1727,108)→(1727,108)へ一致。再現スクリプトtest_reports/audit_coordinates.py。Saturnの個別投影テストも修正前失敗・修正後成功。

## 本番17シーンの経路確認

| シーン | 実体・入力経路 | 判定 |
|---|---|---|
| Fractal | fractal_moving_2.py / 共通frame・座標 | 同型の固定ずれ未検出 |
| Mandala | finger_mandala_3.py / 共通frame・座標 | 同上 |
| Wave Dots | colorfull_wave_dots.py / 共通frame・座標 | 同上 |
| Tree | colorfull_tree.py / 共通frame・座標 | 同上 |
| Jacket | sci_fi_jacket.py / 縦横比維持の縮小検出と共通layout合成 | 同上 |
| Skeleton | skeleton_glitch.py / 共通layout、黒背景 | 同上 |
| Particle Storm | particle_storm_2.py / 2D表示と3D作用点 | 上記確定問題 |
| Spheres | colorfull_dots_spheres.py → spheres_camera.py / 共通frame・座標 | 同型の固定ずれ未検出 |
| Finger Dots | finger_colorfull_dots_2.py / 共通frame・座標 | 同上 |
| Spider | spider_cursor_2.py / 共通frame・座標 | 一手時の第2目標オフセットは以前のユーザー採用仕様、誤補正しない |
| Grid | finger_grid_interaction_2.py / 共通frame・座標 | 同型の固定ずれ未検出 |
| Saturn | saturn_particles_2.py / 元比率保持＋投影係数補正 | 今回実機OK |
| Prism Skin | prism_skin.py / 共通frame・座標 | 同型の固定ずれ未検出 |
| Polygon手 | polygon_vibes_stage.py / 共通frame・座標 | 面の浅い立体変形は演出、指マーカーは画面座標 |
| 万華鏡 | kaleidoscope_camera.py / 共通frame後に意図的な鏡像変形 | 模様上の指位置と操作カーソルの不一致は仕様上起きる。Next/Backは元映像座標 |
| Polygon顔 | polygon_face_stage.py / 共通frame・座標 | 顔入力と操作用手入力は別、同型の固定ずれ未検出 |
| Living Mosaic | living_mosaic.py / 元比率でfit、面平均色 | 意図した分割・頂点変形あり、操作カーソルは元映像座標 |

「未検出」は静的経路確認の結果であり、全シーンの実機再合格を意味しない。独立した検出器間のモデル精度差・遅延は残り得る。

## 条件付きリスクと旧資産

- Particle Stormの入力縮小は現在の1920×1080出力・1280×720カメラなら640×360で比率一致。ただし出力とカメラの比率が変わると再び歪む可能性。元比率維持が望ましいが今回未変更。
- 旧particle_storm.py、saturn_particles.py、visual_monitor_3d.py、roulette_game_advanced.pyに640×480指定あり。現在の共有カメラProxyでは画像変形となる。これらは本番リスト外。
- 旧polygon_vibes.py、polygon_vibes_face.py、earth.py等は独自ワールド座標や固定16:9カメラを使用。本番採用時にそのまま流用しない。
- shared_camera.pyの物理入力サイズ指定、camera_probe.pyの検査設定はシーンの強制変形とは別。検索一致だけで修正対象にしない。

## 次の最小作業

Particle Stormだけの3D作用点係数を修正候補とし、中央と左右上で粒子の反応位置を目視確認。力の強さ・Z挙動・表示カーソル・Managerは変更不要。今回の依頼は横断確認なので、合格済みParticle Stormは維持した。
