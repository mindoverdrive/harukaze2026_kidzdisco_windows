# Acer 1台で操作し、Xiaomiへ最初の1シーンを出す

対象は `finger_colorfull_dots_acer.py` → `finger_colorfull_dots_2.py`。候補ブランチは `codex/rebirth2026-production-candidate`。**現行方針はAcer Windows 11の1台で実行・制御・出力し、DISPLAY1を操作管理、Xiaomiの観客用拡張ディスプレイ2（OS内部名DISPLAY5）を観客映像専用にする。Macは本番対象外。Bluetooth PANとMac–Acer間のネットワーク検証は中止し、追加調査・設定変更を行わない。**

Xiaomi向け専用入口は新しい候補で、実機合格・安定版ではない。従来のprimary画面での試験結果と、これから行う2画面・DPI・Xiaomi上の目視確認を区別する。

## Xiaomi向け候補の起動

1. AcerにC922n USBカメラとXiaomiを接続し、Windowsの拡張表示でDISPLAY1を操作用の主画面、Xiaomiを観客用の2枚目にする。現在のXiaomiのOS内部名はDISPLAY5で、内部番号2を意味しない。C922nのWindows検出名は `c922 Pro Stream Webcam`。別のシーンやTouchDesignerがカメラを使っている場合は、その作業を保存して通常終了する。
2. 既存シーンを動かしているPython環境を指定する。依存関係を勝手に更新しない。
3. このリポジトリの `Start Rebirth Acer.cmd` から確認・起動する。入口は `scripts/start_kids_test.py --audience` と `configs/rebirth_acer_xiaomi.json` を使う。既存の映像用Pythonを `KIDZDISCO_PYTHON` で明示する。

PowerShellで既存の映像用環境を指定する例。このPython 3.12.10は従来候補のpreflight・実C922n試験で使用した環境であり、新しいXiaomi向け入口の実機合格を意味しない。環境変数の指定と起動は同じPowerShellで行う。

```powershell
Set-Location -LiteralPath 'C:\Users\go\Documents\ChatGPT\New project'
$env:KIDZDISCO_PYTHON = 'C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe'
& '.\Start Rebirth Acer.cmd' --check
& '.\Start Rebirth Acer.cmd'
```

`--check` は依存ライブラリ・MediaPipe Hands APIと2画面構成を読み取りで確認し、カメラやウィンドウを開かない。結果は `test_reports/kids_preflight_*.json`。起動・目視成功を意味する検査ではない。

設定は `DISPLAY_TARGET=audience`、`DISPLAY_NAME=\\.\DISPLAY5`、`CONTROL_DISPLAY_NAME=\\.\DISPLAY1`。OS画面名で照合し、DISPLAY1がprimary、観客側のDISPLAY5がnon-primaryで、両者が重ならない拡張領域であることをカメラ取得前に検証する。解像度・座標は実モニターから解決する。第2画面がない、名前や配置が条件と違う場合は終了コード2で止まり、primaryへ自動的に出し直さない。OS画面名と実際のXiaomiの対応は人間が確認する。

HDMI接続後のscreeninfo読取は、操作側DISPLAY1が座標(0, 0)・1920×1080・primary、Xiaomi側DISPLAY5が座標(1920, 0)・1920×1080・non-primaryだった。新しい `--audience --check` は実機で成功し、EDID名 `Mi TV(XMD)` も確認した。これは依存・表示構成の読取結果であり、実映像出力・DPI・リフレッシュレートの合格ではない。接続ポート等の変更後は `--check` の検出結果と設定JSONの名前を照合し、内部番号2に固定して判断しない。不一致の場合は起動を止めたまま対応を確認する。

通常起動時は試験IDごとのログ/メトリクスを `test_reports/kids_trial_*/` に保存する。30分で止めるには `& '.\Start Rebirth Acer.cmd' --duration-minutes 30`。切替反復と長時間試験は [ENDURANCE_TEST_PLAN.md](ENDURANCE_TEST_PLAN.md) を参照。12時間試験はまだ開始していない。

通常起動ではAcerローカルの操作UIも有効になる。起動ログの `[Operator]` 行のURLを `#token=` 以降も含めて、**DISPLAY1上のAcerブラウザ**で開く。audienceモードのUIは `127.0.0.1` に限定され、他のhost指定は拒否する。Manager ControlもDISPLAY1座標へ明示配置する。露出・ズームを観客映像へ適用し、読戻しと見え方を確認してJSON保存する。詳しい操作は [OPERATOR_PANEL.md](OPERATOR_PANEL.md) を参照。

Managerを直接起動する場合も、同じ映像用Pythonを指定する。UIを有効にするには `--operator-port` が必要。

```powershell
& $env:KIDZDISCO_PYTHON manager.py --config configs/rebirth_acer_xiaomi.json --operator-port 8766
```

1シーンだけを起動し、先読み・拍手などのジェスチャー切替・遷移演出を無効にしている。UIの「次のシーンへ」も、この設定では同じシーンを起動し直す。観客映像はXiaomiの観客用拡張ディスプレイ（現在の内部名DISPLAY5）全面へ出し、操作UIとManager ControlはDISPLAY1へ置く。Managerが物理カメラを1つだけ所有し、子シーンはその共有メモリへ接続する。C922名を特定できなければ停止する。

起動後のディスプレイ切断・再配置に対してOSが映像ウィンドウをDISPLAY1へ移すかは未確認。起動前の検証を、切断時の表示維持まで確認した結果として扱わない。

## 従来のprimary画面での机上確認

`Start Kids Test.cmd` は従来どおり `configs/kids_test_acer.json` を使い、Acerのprimaryへ基準シーンを表示する。Xiaomi向け入口の失敗時に自動で使われるものではない。机上確認を明示的に行う場合だけ、同じPython指定の後で使用する。

```powershell
& '.\Start Kids Test.cmd' --check
& '.\Start Kids Test.cmd'
```

## 従来構成の試験記録と旧Mac方針の履歴

候補プロファイルは1280×720、MJPG、30fps要求、露出-5。初回フレーム取得後に露出が-4へ戻る事象を確認し、指定値の補正後は基準シーンで30.719秒・約30fps・途中終了なし・正常終了を確認した。詳細は [C922_EXPOSURE_DRIFT_20260906.md](C922_EXPOSURE_DRIFT_20260906.md) を参照。当時の回帰は84件。この実測を後続修正の実機再検証とは扱わない。

`91b3200`では自然復帰と正常な切替の回数を分離し、全回帰120件がPython 3.11と既存映像venv 3.12.10の両方で成功した。従来構成のC922n実30分は正常終了・資源残留なしだったが、途中の切替とEsc復帰を含み、30分無中断は未合格。同一dots20回の実切替結果も、今回のXiaomi向け入口より前の証拠として保持する。試験IDと限界は [継続検証記録](WINDOWS_VENV_RUNTIME_CHECK_20260906.md) を参照。旧94件とpreflightの根拠は [P1完了監査](P1_CANDIDATE_COMPLETION_AUDIT_20260906.md) に保持する。

以前は `Check Mac Connection.cmd` によるカメラなし疎通と、Macからの操作UI接続を検討・試験した。Acer内のHTTP成功はMac通信成功を意味せず、Macからの実通信は未確認のまま中止した。証拠は上記の継続検証記録と [OPERATOR_PANEL.md](OPERATOR_PANEL.md) の履歴へ保持する。これらは現在の起動手順・本番条件ではなく、Mac/PANの追加検証は行わない。

部屋の暗さを含むFPSの追加調査は後回しにする。現行方針ではDISPLAY1のAcerローカルUIから、Xiaomi上の明るさ・残像・反応を見ながら露出を調整し、採用値を保存する。上の-5や30fps要求を現場の合格値と固定しない。

## 子供が遊ぶ前の確認

1. 大人が2画面の実対応を確認する。DISPLAY1にManager Control・操作ブラウザ、Xiaomiの観客用拡張ディスプレイ2（現在の内部名DISPLAY5）に観客映像だけが全面表示され、DPI・倍率・位置にずれがないこと。
2. 起動ログに `READY`、`START`、`START_ACK`、正の `frame_id` を持つ `FIRST_FRAME` が順に出る。
3. 映像がC922nの実映像であることを確認。Xiaomiの中央、左上、右上、左下、右下で指先に白い円とドットの反応が重なるか確認する。左右反転・上下のずれ・余白への反応がないこと。
4. 一人、二本の手、二人、退出、再入場を短く試す。最初は大人が確認し、その後に子供が反応の位置・遅延を理解できるかを見る。
5. 短い目視確認後、操作による切替を混ぜない時間を確保して30分の単一シーンを確認する。切替反復・USB復帰・Xiaomi長時間運転はそれぞれ別の試験として記録する。
6. DISPLAY1の操作UIの「Managerを終了」、Manager Controlの `q`、またはコンソールのCtrl+Cで全体終了する。シーンだけでEsc/qを押すとManagerは次の同一シーンを起動し得る。
7. 終了後、今回のManagerとその子PIDが残らず、もう一度同じ起動ができることを確認する。

映像は一度だけ左右反転し、その同一フレームを認識と表示に渡す。表示余白・倍率のレイアウトも同一の値を使い、指先は表示されたカメラ領域内へ変換する。これはコード/自動試験での保証であり、表示DPI・ドライバー・実カメラ遅延を含む実機目視の代わりにはならない。

## 未完了と失敗時記録

- 従来構成で確認済み: 既存映像用Pythonのpreflight、実C922nの取得と初回描画、操作を含む30分運転、修正後の同一dots20回交代とEsc復帰3回、終了後の所有PID/共有メモリ解放。新しいaudience入口・Xiaomiでの実機合格とは区別する。
- `PB-01` は解消済み。その後Codexのlean-ctx連携を解除し、通常ツールから既存映像用Pythonのpreflightを再確認した。現在の実行方法と解除範囲は[解除・整合性記録](LEAN_CTX_REMOVAL_20260906.md)を参照。PATHのPython 3.11には映像用依存がないため、上の実行環境を指定する。
- `HUMAN_CHECK_REQUIRED`: 2画面の実対応・DPI・操作管理と観客映像の配置、C922nとXiaomi上の5点一致、複数人・子供の遊びやすさ、単一30分、Xiaomi構成での切替反復、異種シーン切替、USB再接続、Xiaomi長時間運転、画面切断時のOSによるウィンドウ移動。短時間の成功だけでは合格としない。Mac通信は現在の本番条件に含めない。
- 従来の操作UIからの実機適用・復元・プレビューJSON保存・Next・終了はAcer内で確認済み。新しい設定JSONの保存・再起動と、Xiaomi上の画角・見た目は別途確認する。
- 30分の基本動作確認後、大人がC922n切断→再接続を確認する。P1 #3は疑似カメラによる再取得・停止試験に通過したが、実USBでの復帰は未確認。12時間試験は基本確認と切替反復の後に行う。

失敗時は、preflight JSON、起動から終了までのコンソール、Camera diagnostic、各制御イベントとPID、両画面のOS名・primary状態・座標・サイズ・DPI、C922nのUSB接続、試した人数、期待した反応と実際の反応を残す。共有する記録から操作URLのトークンを除く。録画はこのツールでは自動取得しない。

## ロールバック

まずManagerを通常終了する。カメラ調整だけを戻す場合は [OPERATOR_PANEL.md](OPERATOR_PANEL.md) の手順で変更前の値を適用・保存する。候補全体を戻す場合は、試す前の実行場所・設定から起動し直す。Gitの共有履歴を消す操作は不要。候補ブランチの変更を戻す必要がある場合は、作業ツリーを確認して対象コミットを `git revert` する。mainへの統合はまだ行っていない。
