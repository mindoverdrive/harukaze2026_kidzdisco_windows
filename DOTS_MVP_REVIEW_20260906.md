# Finger Colorful Dotsの成人基礎操作・30分試験

2026-09-06。`finger_colorfull_dots_acer.py`（呼出先 `finger_colorfull_dots_2.py`）をAcer Windows 11、C922n、Xiaomiの観客用拡張画面で実行し、OS再起動後の新規試験で成人による基本操作と30分運転を確認した。実機担当から受領した人間の回答とランタイム観測を分けて記録する。今回の文書更新ではコード・設定・Git・実機を操作していない。

**判定：照明あり・露出-4／zoom 176の比較条件で、成人の中央操作、四隅の座標一致、退出・再入場、両手同時操作、および単一シーン30分運転が合格。** 子供、2人同時、暗所、USB抜き差し、12時間、gridへの切替後の残留は未確認で、本番採用・安定版の合格判定には広げない。終了コードは0で対象資源も残らなかったが、scene終了処理とrunner通知に例外記録があるため「完全無エラー」とはしない。

## 確認条件

| 項目 | 実際の確認条件 |
|---|---|
| 実行機 | Acer Windows 11。OS再起動後、再起動前のPython PIDが0であることを確認してから新規起動 |
| trial | `test_reports/kids_trial_20260906_204802_629994100` |
| 入力 | C922n USBカメラ。起動診断は1280×720・要求30fps・MJPG、実測30.01fps |
| 観客映像 | Xiaomiの拡張ディスプレイ。OS内部名 `\\.\DISPLAY5` |
| 照明 | 手に光が届く照明あり条件。照度のlux値は未記録 |
| 露出・ズーム | OS再起動後は実値が露出-5／zoom 100へ戻った。比較用にAPIで露出-4／zoom 176を一時適用 |
| 永続化 | JSON保存なし。露出-4／zoom 176を次回起動でも自動適用される保存済み値として扱わない |

AcerのDISPLAY1が操作管理、Xiaomiが観客映像という本線を維持する。Macは本番対象外で、Bluetooth PANやMac–Acerネットワークの検証は再開しない。

## 人間が確認した操作

| 項目 | 確認した動作 | 結果 |
|---|---|---|
| 中央 | 中央で指を動かすと白い円が追従し、指の近くの波が反応する | OK |
| 四隅 | 左上・右上・左下・右下で映像と操作の座標が一致する | OK |
| 退出・再入場 | 手を外すと白い円が消え、自律波は続く。手を戻すと白い円が再び出る | OK |
| 両手同時 | 左右の人差し指それぞれに白い円が出て、両方の近くで波が起きる | OK |

これは実際の表示に対する成人の目視確認である。両手同時は一人の成人による確認であり、2人同時操作、手の交差・遮蔽、全フレームの不検出ゼロ、遅延の数値保証、すべての手の向き・速さへの対応を確認した試験ではない。

## 30分運転と終了確認

`duration_reached`で終了し、exit 0、`trial_elapsed=1800.672s`だった。カメラは全区間で `read_failures=0`、`reopen_attempts=0`、`last_error=null`、`max_frame_gap=0.079s`。179件のSceneMetricsはfps最小23.36、中央値27.46、最大35.2だった。C922n起動診断の30.01fpsとは測定対象・区間が異なるため、同じ指標として比較しない。

暖機後のscene working setはfirst 228,442,112 bytes、last 241,893,376 bytes、min 225,132,544 bytes、max 241,893,376 bytes。scene handlesはfirst 660、last 655、min 653、max 660。Manager working setはfirst 164,925,440 bytes、last 159,178,752 bytes、min 158,830,592 bytes、max 164,925,440 bytes。Manager handlesはfirst 895、last 887、min 886、max 895だった。終了後は対象PID、対象窓、共有メモリの残留なしを確認した。

ただし、scene終了時にMediaPipeの `wait_until_idle` で `KeyboardInterrupt`、runner側に `ERROR notification failed: ConnectionAbortedError` が記録された。30分運転中のカメラ取得や再接続の失敗ではなく、最終的なtrial終了コードと資源解放は正常だったが、完全無エラーの試験とは記録しない。

## Spheresとの関係

Spheresも照明ありで同じ成人基礎3項目を合格している。一方、暗い条件では中央の「反応なし」「白い円も出なかった」という不合格があり、照明を明るくした後に復帰した。詳細は [Spheres MVP確認](SPHERES_MVP_REVIEW_20260906.md) に保持する。

Dotsの今回の合格をSpheresの暗所不合格の解消へ流用せず、Spheresのfps・保存入力の検出結果をDotsへ流用しない。両シーンとも実際に遊ぶ位置の手に十分な光が届くことを、次の確認でも条件として残す。

## 残る実機確認

| 項目 | 状態 |
|---|---|
| 子供が操作と反応を理解して遊べるか | 未確認。成人の結果から代用しない |
| 2人同時、手の交差・遮蔽 | 未確認。成人一人の両手同時はOK |
| 暗所 | Dotsでは未確認。Spheresでは暗所不合格の履歴あり |
| USB抜き差し・番号変化 | 未確認 |
| 長時間・12時間 | 未確認 |
| grid実機 | 後続試験で成人の基本操作と両手操作を確認済み。詳細は [Grid MVP確認](GRID_MVP_REVIEW_20260906.md) を参照 |

再起動・停止の既存手順は [KIDS_TEST_START.md](KIDS_TEST_START.md) と [OPERATOR_PANEL.md](OPERATOR_PANEL.md) を参照。Dotsの既存入口は `Start Rebirth Acer.cmd --scene dots`。露出-4／zoom 176は未保存なので、同条件で比較する場合は起動後の適用・読戻しを別に記録する。次はparticle_stormの安全な起動入口を整備してから実機確認する。トークン付きURLや一時認証値はこの資料へ記載しない。
