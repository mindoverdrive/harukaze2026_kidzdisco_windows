# spheres 86590ee 再起動・指反応の目視準備

2026-09-06。ユーザーの依頼は、候補86590eeを確実に再起動し、人間が指の反応と表示位置の一致を目視確認できる状態にすること。17:02:48の新起動は成功し、表示を続けたまま人間の確認待ちで作業を停止した。指の反応・位置一致と、旧セッションの終了事象の解明は未完了。

## ユーザー申告

状態：**安定性の要確認事項。原因未解明で、今回の目視試験では修正・再現操作を行わない。**

- 終了のためにキーを押すと2回再出現し、3回目で消えたとの申告があった。
- 音声書き起こしは「9」だが、実際の入力がQか数字9かは未確定。
- 各打鍵の時刻、フォーカスがあったウィンドウ、実際に押されたキーは未確認。書き起こしをキーイベントの記録として扱わない。

以下のログと申告は別の根拠として保存する。回数が似ていることから、各打鍵と起動・終了イベントを一対一に対応付けない。

## 旧セッションのログで確認した事実

対象は `test_reports/kids_trial_20260906_155744_219024000/runtime.jsonl` の末尾。時刻はJST。この旧セッションの記録を、新しい86590eeの起動結果へ読み替えない。

| 時刻 | 記録された出来事 |
|---|---|
| 16:49:51～16:49:53 | wrapper 6828／scene 1568がREADY・START・START_ACKを経てFIRST_FRAMEに到達。FIRST_FRAMEの記録値は2.250秒、frame_id 93695。その後、旧wrapper 21108にscene_switchによる停止要求。 |
| 16:49:55～16:49:56 | wrapper 6828のscene_exit後にwrapper 19508／scene 14064が起動し、FIRST_FRAMEに到達。記録値は1.547秒、frame_id 93786。 |
| 16:49:58 | wrapper 19508のscene_exit後、wrapper 29144／scene 14480が起動。READY・START・START_ACKを記録。 |
| 16:49:59 | 最後の候補は `control connection closed before FIRST_FRAME` でFAILED。FIRST_FRAMEはなく、candidate_discardによる停止要求。 |
| 16:49:59 | run_errorの理由は `no running scene after candidate failure: control connection closed before FIRST_FRAME`。 |
| 16:50:00 | run_endはreason=error、exit_code=1、completed_switches=2、completed_promotions=4。 |

この末尾から確認できるのは、シーンの退出と再起動があり、最後の候補が初回フレーム前の制御接続閉鎖で失敗し、Managerがエラー終了したこと。閉鎖した理由とユーザーのキー操作との因果は未確定である。正常終了や、すべてのOS／GPU資源が解放された証拠として扱わない。

completed_switches／completed_promotionsはManagerの切替・昇格集計であり、打鍵回数や画面の再出現回数と同一ではない。FIRST_FRAMEの秒数はscene_control.detail.elapsed_sで、Manager全体の経過時間とは別である。

## 新しい起動と人間による目視の記録欄

新起動は17:02:48。HEAD/sourceは `86590ee247cde7a61dcff674eb972b80d6d96a65` で、担当が `git diff --quiet 86590ee` の成功と11ファイルのSHAを確認した。根拠は `test_reports/spheres_retrial_86590ee_source_manifest_20260906.json`、起動記録は `test_reports/spheres_retrial_86590ee_session_20260906.json`。既存Python 3.12.10 venvを使い、プロセス限定で `PYTHONPYCACHEPREFIX` を未存在の専用パス、`PYTHONDONTWRITEBYTECODE=1` として既存pycを使用しない起動にした。

| 確認項目 | 現在の状態 | 残す内容 |
|---|---|---|
| 起動元 | 照合・新起動成功 | 86590ee、試験ID `test_reports/kids_trial_20260906_170252_17028700` |
| 起動の実体 | FIRST_FRAME到達 | Manager 29272、起動launcher 3552、scene 9504、wrapper 22496。FIRST_FRAME 3.687秒／frame_id 106 |
| 表示先 | 窓配置を観測 | SKYで球体窓26347160が1つ、Manager窓12192726が1つ。球体は1920×1080、原点(1920,0)。見切れ・操作位置の目視は別途 |
| 指の反応 | 人間の確認待ち | 指に反応するか、追従するか、遅延や反応の途切れ |
| 表示位置との一致 | 人間の確認待ち | 中央・左上・右上・左下・右下での指と反応位置の一致 |
| 終了時の観測 | 今回は未実施 | 表示継続中。終了時はブラウザ操作画面の「Managerを終了」を使い、Q／9の再現は行わない |

新起動のC922は名前一致・index 1・DSHOW・MJPG 1280×720。診断は2秒59フレーム、29.48fps。露出は既存設定-5を通常適用し、新しい調整は行っていない。17:04:08のsampleは取得失敗0・再接続0・switch 0・promotion 1・error null。17:04:09のrenderは48.75fps、hands 0だった。過去と条件の揃った速度比較ではなく、手の反応や操作一致の合格にも使用しない。

自動終了・自動切替の試験指定はない。人間はまず手首まで掌を映し、中央で人差し指をゆっくり左右・上下へ動かして、白い円と近傍の波・発光が反応するか確認する。中央が確認できた後だけ四隅へ進み、白い円と映っている指先の位置を比較する。確認結果が届くまで表示を継続し、追加の自動操作は行わない。

この資料の編集担当はログ読取とMarkdownの更新だけを行い、新起動の事実は起動担当から受領した。今回、推測によるコード修正やQ／9操作の再現は行っていない。

回転軸の見え方や過去の手なしFPS改善は、指反応・位置一致・複数人・子供・30分／12時間の合格へ流用しない。Bluetooth PANとMac–Acerネットワーク検証の中止方針は維持する。トークン付き操作URLはこの資料へ記載しない。
