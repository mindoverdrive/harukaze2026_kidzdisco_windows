# Jacket 30分採用試験

- 証拠: test_reports/kids_trial_20260907_215526_338480900/runtime.jsonl および scene_output.jsonl。
- 2026-09-07 22:25:33、duration_reachedで終了。試験1800.531秒、Manager exit_code 0、昇格1回・切替0回。
- 終了要求直後、MediaPipe wait_until_idleでKeyboardInterruptを記録。30分完走と「例外なし」は区別し、終了処理を別途確認する。
- ユーザーが最終確認に「はい」と回答。途中の消失・再起動なし、静止時の結晶化、動作時の模様の流れへの復帰を30分目視OKとして記録。
- 複数人・子供による操作は独立した未確認項目。
