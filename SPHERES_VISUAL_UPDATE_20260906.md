# Colorful Dots Spheres：高密度の発光と斜め回転

2026-09-06。対象は実ファイル `colorfull_dots_spheres.py`。ユーザーの「粒子を増やし、滑らかでリッチな画に」「回転軸を斜めへ」という追加指示を反映した候補。作業ブランチは `codex/rebirth2026-production-candidate`、安全基準点 `705b081`、直前の2画面入口は `9e0c1c4`。

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

## 検証

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

このチェックポイント作成時点では新球体のXiaomi試写は未実施。次に、短時間の初回表示・実render fps・camera更新・終了再取得を確認する。斜め回転の見え方、光量、操作位置、複数人、子供の理解、単一30分・切替反復・12時間はHuman Check Required。既存dotsの継続表示を球体の合格へ流用しない。

Bluetooth PANとMac–Acer接続検証は完全中止のまま。ネットワーク設定・購入・本番昇格は行わない。復帰はdots入口 `Start Rebirth Acer.cmd`、コードは候補commit単位のrevert、全体基準は `705b081`。main/stableの強制変更は行わない。
