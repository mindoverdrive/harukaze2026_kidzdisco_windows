# 採用試験チェックポイント

3シーンとも30分完走し、ユーザーが最終目視確認に回答した。

| シーン | 試験秒数 | 目視 |
|---|---:|---|
| Skeleton | 1800.578 | 黒背景・骨格追従・退出再入場・全画面・往復切替OK |
| Jacket | 1800.531 | 静止結晶化・動作再開・途中消失や再起動なしOK |
| Mandala | 1800.578 | 色変化・外側へ拡散消失・再描画OK |

各試験の最終カメラ計測は取得失敗0、再接続0。対象シーンとManagerのPID残留なしを確認。

## 終了時のTraceback

3試験ともduration_reachedの停止要求直後にKeyboardInterruptを記録。manager.pyの_kill_processはWindowsでCTRL_BREAK_EVENTを送り、scene_profile_runner.pyはSIGBREAKをsignal.default_int_handlerへ登録する。観測はこの停止経路と整合しており、途中の自発的クラッシュを示す記録ではない。

3シーンのfinallyはExitStackでカメラ、MediaPipe、Pygameの解放を行う。Managerのexit_code 0とプロセス不在も確認。ただしGPU解放の個別計測や12時間リーク検証まで証明したとは扱わない。終了Tracebackの表記改善は未実施。今回、停止ロジックは変更しない。

## 差分と保留

- 一時追加したSkeleton検出ログを除去し、製品コードはa0cf2f0と同一。採用試験とTree二手目視、トランジション完成判断の記録のみ保存する。
- 子供、実際の複数人、現場条件、12時間連続運転はそれぞれ未確認。
- 本番プレイリストは変更しない。a0cf2f0が製品コードのロールバック基準。
- 初回unittest discoverはモックの読み込み順によるnumpy.__spec__/pygame初期化エラー2件。既存のnumpy・pygame先読み手順で再実行し、475件中451成功・24スキップ・失敗0。証拠: test_reports/adoption_checkpoint_preloaded.log。
