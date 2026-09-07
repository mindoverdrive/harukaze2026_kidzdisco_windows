# Mandala 30分採用試験

- 証拠: test_reports/kids_trial_20260907_223013_651400/runtime.jsonl と scene_output.jsonl。
- 23:00:20にduration_reachedで終了。試験時間1800.578秒、Manager exit_code 0、昇格1回、切替0回。
- 終了要求直後のcv2.cvtColor中にKeyboardInterruptあり。完走と例外なしを区別し、終了処理の確認事項として残す。
- 最終確認にユーザー「はい」。色の緩やかな変化、線の外側への拡散・消失、再描画が続く状態を30分目視OKとして記録。
- 子供・実際の複数人の操作は別途未確認。
