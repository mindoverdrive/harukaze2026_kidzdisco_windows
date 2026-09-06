# Stormのタスクバー露出：再現と最小修正

## 05:47：修正版を実シーンで再測定、人間の再確認待ち

- 修正コミット `096bace` を候補へpush後、既存Manager内でStorm→Spheres→Stormを担当エージェントがAPIから一回ずつ実行。2方向の目視をユーザーが合格したとは数えない。
- 現StormはPID10920/wrapper27308、FIRST_FRAME05:46:28（4.250秒）、Manager6788/SHM維持、switch_count3/promotion_count4、camera failure/reopen0、露出-4/zoom176。旧Storm15576/wrapper23816、中継Spheres26492/wrapper22660の稼働なしを確認。
- 05:46:48の同じ実測probeでclient/outer=(1920,0)〜(3840,1080)、下端3点ともStormのGLFW窓がヒットしexit0。SecondaryTrayはStormより後ろ、topmost=false。Stormもtopmost=falseで、最前面固定やOS設定変更はしていない。実測時のStormはforeground=trueなので、次はAcer側クリック後の人間の見え方を確認する。
- 根拠 `test_reports/audience_cover_20260907_054648.json`、`window_observation_20260907_054648.json`。同trialの05:49:49頃の上限は維持。実画面下端と中央反応の再確認まではHuman Check Required。

2026-09-07。修正前の基準点は候補ブランチ `2039b23`、長期安全基準は `705b081`。main/stableを変更しない。

## 実際の不合格

ユーザーがSpheres→Stormの手動切替後に「タスクバーが残る」と回答。手の反応や他の表示項目を同時に合格とは解釈しない。

trial `test_reports/mixed_visual_20260907_051941_163497/trial`。05:36:09のStorm FIRST_FRAME（4.703秒）後に旧Spheres停止要求があり、Manager6788/同じSHMを維持、switch_count1/promotion_count2、camera failure/reopen0。制御上の切替成功と人間の観客表示NGは別判定。

05:37:57のWin32観測でStorm PID15576のGLFW窓は(1919,-7)〜(3839,1056)。想定のXiaomi領域は(1920,0)〜(3840,1080)。下24pxが覆われず、Xiaomi側タスクバーも前面にあった。

`probe_audience_cover_20260907.py 15576` を実行し、client領域不一致と下端のtaskbar hitを実測（exit1）。Win32 WindowFromPointで下端3点を読み、タスクバーの子ウィンドウも親ルートで識別する。これは光学的なパネル観測の代わりではなく、人間のNGに対応するOS上の再現条件。

## 原因の切り分け

候補は①枠を外す前の配置順、②DPI補正、③領域が正しくてもタスクバーが前面に残る、の順。カメラ・WGPU描画・MediaPipeを除いた非表示の実GLFW窓へ、製品の `setup_rendercanvas_fullscreen` を適用すると、同じ(1919,-7)/1920×1063を再現した。

呼出し順が「位置→サイズ→枠を外す」で、最後の枠除去でWin32 client領域が変わっていた。`display_utils.py` のこの処理を「枠を外す→位置→サイズ」に変更。OSのタスクバー設定、最前面固定、カメラ設定、検出/描画ロジック、Pygame経路は変更していない。

## 検証

- 追加した `tests/test_glfw_fullscreen_windows.py` は、非表示・RESIZABLE・NO_APIの実GLFW窓で640×480開始と1920×1080開始の2条件を同じテスト内で確認。カメラもGPUデバイスも開かない。修正前は両条件失敗、修正後は両条件成功（約0.15秒）。
- 元の最小再現スクリプトも修正前exit1→修正後exit0、client/outerが(1920,0)〜(3840,1080)に一致。visible=falseを維持し、診断窓はfinallyで破棄。
- 全回帰はPython3.12で226件・失敗0・skip1。Python3.11の初回並行実行では既存HTTP認証試験が一度WinError10053で失敗。HTTPのみ単独9件成功、続く3.11全回帰226件は失敗0・skip1。10053の原因は未確定で、HTTPコードを変更していない。ローカル記録 `test_reports/taskbar_full_py311_20260907.log`。
- skip1は上の実GLFW試験。通常の全回帰では明示実行を要求し、既存映像Python3.12で `KIDZDISCO_TEST_GLFW=1` を子プロセス内だけ設定して別途成功させた。skipを成功件数に加えない（全回帰の実行合格225件ずつ＋実GLFWテスト1件）。
- 実シーンでの再読込・下端測定・人間の表示確認は次の段階。修正後の非表示窓成功だけでタスクバーMVP mustを解決済みにしない。

## 影響と未確認

同じGLFW helperを使うSaturn等にも配置順が適用されるため、採用する他のGLFWシーンでは観客領域と操作側フォーカスの再確認が必要。Storm左右各240pxの操作不能帯は別問題で未変更。終了時例外、混在反復、USB復帰、子供/複数人、現場条件、12時間も別の保留。

ロールバックは今回の表示修正コミットを候補ブランチ上でrevertし、影響シーンを通常のManager切替で読み直す。`2039b23` は修正前の参照点であり、タスクバー問題がない安定版という意味ではない。強制reset/force pushは行わない。
