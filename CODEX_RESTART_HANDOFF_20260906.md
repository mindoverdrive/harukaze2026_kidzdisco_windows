# Codex再起動用引継ぎ — Rebirth 2026 Acer本線

更新時刻: 2026-09-06 20:33 JST前後

## 安全基準とGit

- 作業ブランチ: `codex/rebirth2026-production-candidate`
- 長期の安全基準点: `705b081`
- この引継ぎ作成前のリモート先端: `0bdfe9b`
- main/stableへの統合、force push、本番昇格は行わない。
- 再開時は最初に `git status --short --branch` と `git log -3 --oneline --decorate` を読み、推測で状態を補わない。
- 無関係な未追跡物 `20260906-current-status.html`、`TD_BUSINESS_RESEARCH_20260906.md`、`status_dashboard/` は変更・stageしない。

## 現在の実機構成

- Acer Windows 11一台で実行・制御・映像出力を完結する。
- C922n USB cameraをManagerが所有し、sceneは共有メモリ経由で読む。
- DISPLAY1は操作管理用。XiaomiはHDMI拡張画面DISPLAY5で、観客映像をfullscreen表示する。
- Mac、Bluetooth PAN、Macとのネットワーク接続は本番構成から外し、追加調査しない。
- 部屋の照明を点灯した条件。C922nの実値は露出-4、zoom 176。露出-4は実行中だけの適用でJSONへ保存していない。

## 現在稼働中の試験

- scene: `finger_colorfull_dots_acer.py` → `finger_colorfull_dots_2.py`
- trial: `test_reports/kids_trial_20260906_202405_903917000`
- 起動時のC922n診断: 1280×720、30fps、MJPG、実測29.98fps。
- 記録時の所有PID: Manager 32700、scene 30648、scene launcher 4376。再開時は必ず実在とcreation timeを確認し、PIDだけで同一プロセスと断定しない。
- 20:32:43時点でelapsed 517.656秒、camera frame 8526、read failure 0、reopen 0、last errorなし、最大frame gap約0.079秒。
- scene metricsは観測範囲で概ね24.8〜33.1fps。
- Codexアプリ再起動でこの外部プロセスが残る可能性がある。再開時に勝手に二重起動せず、既存Manager・scene・共有メモリ・Xiaomi表示を先に確認する。
- operator URLの認証tokenは資料へ書かない。必要なら現行Managerの起動ログからローカルで取得し、出力やチャットへ露出させない。

## 人間が確認済みの範囲

照明あり・露出-4・zoom 176の条件で、ユーザーが次をそれぞれ `ok` と回答した。

1. 中央で白い円が指先に追従し、近傍のdotsが波打つ。
2. 左上、右上、左下、右下で大きな座標ずれや左右反転がない。
3. 手を画面外へ出すと白い円が消え、自律波が続き、手を戻すと白い円が再出現する。

これは成人一人による短時間の基本確認である。子供、二人同時、暗所、30分、USB抜き差し、scene切替後の残留、12時間、本番採用は未確認。

## 再開直後の順序

1. Gitのbranch・HEAD・working treeを確認する。
2. PID 32700/30648/4376、trialの`runtime.jsonl`末尾、Xiaomi表示を確認し、Dotsが継続中か判定する。
3. 継続中なら二重起動せず、次のHuman Checkを一つだけ依頼する: 両手を同時に映し、左右の人差し指それぞれに白い円が出て両方の近傍で波が起きるか。
4. Dotsを合計30分まで継続し、終了時のcamera failure/reopen、fps、working set、handle、終了理由、所有PIDと共有メモリの残留を記録する。30分に達する前にプロセスが消えていた場合は、その事実と最終ログを残し、30分合格にしない。
5. Dotsを終了・切替するときはDISPLAY1のManager操作を使う。scene内Esc/qだけでManagerを残す操作は避ける。
6. 次候補は `finger_grid_interaction_acer.py`。ただし現行 `scripts/start_kids_test.py --scene` はdots/spheresのみで、wrapper直起動ではDISPLAY5と共有カメラ条件を保証できない。既存Manager経路の一時的な1scene専用設定を作る最小変更を先に設計・検証する。本番playlist採用は確定しない。

## 次候補gridの静的確認

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

## 関連資料

- `DOTS_MVP_REVIEW_20260906.md`
- `SPHERES_MVP_REVIEW_20260906.md`
- `SPHERES_RETRIAL_86590ee_20260906.md`
- `PRODUCTION_CANDIDATE_PROGRESS.md`
- `KIDS_TEST_START.md`
- `ENDURANCE_TEST_PLAN.md`

