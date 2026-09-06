# Acer / C922n / Xiaomiの基礎試験と長時間試験

現行方針はAcer Windows 11の1台で実行・制御・出力し、DISPLAY1に操作管理、Xiaomiの観客用拡張ディスプレイ2（OS内部名DISPLAY5）に観客映像だけを全面表示する。入口は `Start Rebirth Acer.cmd`。Macは本番対象外で、Bluetooth PANおよびMac–Acer間のネットワーク検証は中止し、追加調査・設定変更を行わない。

この文書は試験手順で、新しいXiaomi向け入口の実機合格記録ではない。従来のprimary構成の実30分は正常終了したが、操作による切替・退出を含むため単一シーン無中断は未合格。同一dots20回切替の結果も [継続検証記録](WINDOWS_VENV_RUNTIME_CHECK_20260906.md) の試験IDと照合し、今回の2画面構成の合格へ移し替えない。実USB復帰と12時間耐久は未実施。実地入口は [KIDS_TEST_START.md](KIDS_TEST_START.md)。最初の候補は `finger_colorfull_dots_acer.py` のみ。

## 実施順

1. 既存映像用Pythonで `Start Rebirth Acer.cmd --check` を実行し、依存とOSの2画面情報を読み取り確認する。カメラ・ウィンドウは開かない。別のカメラ利用アプリを保存・通常終了してから候補を起動する。
2. 大人が2画面の実対応とDPIを確認する。DISPLAY1が操作管理、Xiaomiの観客用拡張ディスプレイ2（現在の内部名DISPLAY5）が観客映像専用で、管理画面が観客映像へ出ないことを別項目として記録する。
3. Xiaomiの中央と四隅でC922nの実映像と指先の5点一致、一人→二人→退出→再入場を確認する。最初は大人が短く確認し、その後子供に遊んでもらう。
4. 操作を混ぜない時間を確保し、30分の単一シーンを確認する。意図的な切替・USB抜去・ディスプレイ切断を混ぜない。
5. Xiaomi構成で同一シーンを20回切り替える。Managerと共有メモリ名を維持したまま、稼働シーンのJob/PIDだけが交代するか確認する。
6. 大人がUSB切断／再接続と終了→再起動を別試験で確認する。画面切断・再配置時にOSがウィンドウを移す挙動も、無中断試験に混ぜず別の確認として記録する。
7. 選定済みの異なるシーン間を確認し、基本試験の合格を人間が記録してから、Xiaomiを観客出力に使った長時間試験へ進む。最終の暫定目標は12時間だが、まだ実行していない。

## コマンド

以下はリポジトリのPowerShellから実行する。`KIDZDISCO_PYTHON` の選択方法はKIDS_TEST_START.mdを参照。新入口は `scripts/start_kids_test.py --audience`、設定は `configs/rebirth_acer_xiaomi.json`。

OS名 `\\.\DISPLAY1` がprimary、観客側の `\\.\DISPLAY5` がnon-primaryで、重ならない拡張領域であることをカメラ取得前に検証する。解像度・座標は実モニターから解決する。名前・配置の不一致や第2画面不在は終了コード2とし、primaryへ自動表示しない。操作UIは `127.0.0.1` に限定し、起動ログのURLをDISPLAY1のAcerブラウザで開く。Manager ControlもDISPLAY1へ配置する。

HDMI接続後の実読ではXiaomiの内部名がDISPLAY5、EDID名が `Mi TV(XMD)` で、新しいaudience preflightは成功した。これはカメラなしの依存・表示構成検査で、実映像・DPI・長時間運転の合格ではない。用途上の2枚目を内部番号2へ固定せず、接続ポート等の変更後は `--check` の検出名と設定JSONを照合する。

```powershell
# 30分の単一シーン。最初のFIRST_FRAME後から計時し、通常の終了処理へ進む。
& '.\Start Rebirth Acer.cmd' --duration-minutes 30

# 同じ基準シーンを20回切替。20秒ずつ見て、最大30分で終了する。
& '.\Start Rebirth Acer.cmd' --switch-every 20 --switch-count 20 --duration-minutes 30

# 基礎合格を記録した後だけ実行する12時間試験。今回まだ実行していない。
& '.\Start Rebirth Acer.cmd' --duration-minutes 720
```

同じ候補JSONを指定してManagerを直接起動する場合の例（2画面配置を実機確認してから）:

```powershell
& $env:KIDZDISCO_PYTHON manager.py --config configs/rebirth_acer_xiaomi.json --operator-port 8766 --report-dir test_reports\chosen_scenes_run01 --switch-interval-seconds 60 --switch-count 20
```

既存のmetadata.jsonがあるreport-dirは再利用を拒否する。試験ごとに新しい名前を付ける。子供の操作中は意図しない自動切替を避け、まず単一シーンで試す。

従来の `Start Kids Test.cmd` と `configs/kids_test_acer.json` は、primary画面での机上確認用として保持する。Xiaomi向け検証に失敗したときの自動代替にはしない。既存primary試験の結果と新しいXiaomi構成の試験IDを分ける。

## 記録されるデータ

共通ランチャーは試験ごとに `test_reports/kids_trial_<日時>_<ID>/` を作る。使用した入口とconfigを記録し、従来のprimary試験とXiaomi向け試験を区別する。

- `metadata.json`: コミット、作業ツリーがdirtyか、解決済みconfig、Python。実カメラ/目視確認の初期状態はfalse。合格に自動昇格しない。
- `runtime.jsonl`: 起動制御イベント、実Python PIDとランチャーPID、共有メモリ名、10秒ごとのフレーム番号/最終成功からの経過/最大フレーム間隔、再取得回数、終了理由、切替回数。
- 同じsample内にPrivate Bytes、Working Set、累積CPU時間、ハンドル、GDI/USERオブジェクトをPID別に記録。取得できない項目はunavailable/nullで残す。PID再利用を識別するcreation_ticksも記録する。
- `scene_output.jsonl`: 子シーンのstdout/stderr。`[SceneMetrics]` はカメラ処理と描画APIが成功した呼出しの10秒平均FPS。実パネルの表示更新を測った値ではない。
- `[SceneLifecycle]` の `exit_request` / `runner_end` はQUIT・Esc・q・Python終了を区別する。Managerの `scene_stop_request` / `scene_exit` とlaunch_id・実PID・launcher PIDで照合する。runner終了の記録だけでOS資源解放完了とは判定しない。
- `91b3200`以後の `sample.switch_count` / `run_end.completed_switches` は、旧シーン生存とFIRST_FRAME後の停止成功を伴う交代数。初回と自然復帰は全昇格の `promotion_count` / `completed_promotions` にだけ含む。以前のログは定義が異なるので混在させない。

各ログは5MiB×現行1ファイル＋世代3ファイルの上限。2種類合わせて約40MiB（最後のレコード分は超過し得る）。長時間の大量エラーで古いログが循環した場合、初期の測定が残っているとは限らない。metadataは別保存。子の出力は読み捨てず逐次排出し、終了済みの読取スレッドを保持し続けない。データの書込失敗は試験失敗として停止処理に進む。

GPUメモリ、温度、物理パネルの表示FPS、入力から反応までの遅延は自動取得していない。タスクマネージャー等で同じPIDとGPUエンジンを確認し、手動観測として時刻付きで記録する。撮影や人物画像の自動保存は行わない。

## 暫定合格条件

### 2画面・DPI・操作位置

- OS名・primary状態・座標・解像度と実際のAcer／Xiaomiを照合する。DISPLAY1にManager Controlとローカル操作ブラウザ、Xiaomiの観客用拡張ディスプレイ2（現在の内部名DISPLAY5）に観客映像だけが全面表示される。
- 両画面のDPI／倍率を記録し、ウィンドウ位置・余白・映像と指先の中央／四隅の5点一致を実機で確認する。共通layoutの自動試験だけで目視合格にしない。
- 設定適用・保存・通常終了をDISPLAY1で扱い、観客画面へ管理画面が出ないことを確認する。
- 画面切断・再配置時のOSによるウィンドウ移動はHuman Check Required。起動前の画面検証を、その後の切断耐性の合格として扱わない。

### 30分単一シーン

- 初回起動後の30分を完走し、予期しない終了・再起動・切替が0回。
- 起動後のManager PID、稼働シーンのJob内実Python PID、共有メモリ名が同じ。
- 意図的な切断を含まない試験で、2秒を越えるフレーム更新停止がない。
- 処理/描画API呼出しの10秒平均と、実カメラの到着FPSを別々に記録し、Xiaomi上で操作位置と反応を追えるか確認する。旧案の30FPS下限は、現在の暗い部屋で原因調査を続ける条件にはしない。露出等は試験前にDISPLAY1のAcerローカルUIから調整し、照明・残像・反応を含めて人間が判定する。会場でのFPS合格値は未確定として残す。
- Private Bytesの5〜10分中央値と25〜30分中央値を比較し、増加が10%または50MiBの大きい方を越えたら原因調査。閾値内でも一方向に増え続ける場合は保留。
- ハンドル、GDI/USER数、GPUメモリに継続増加がない。終了後に対象PID/画面が消え、再起動でC922を取れる。

### 20回切替

- 各回に正しいlaunch_idのFIRST_FRAMEがあり、旧シーンはそれより前に終了しない。
- 20回完走。終了理由が `switch_count_reached`、`completed_switches=20`。
- 切替ごとに物理カメラの再取得が起きず、同じ共有メモリ名を使う。
- 遷移/先読みを含むJobが定常数に戻り、終了済みPIDが積み上がらない。Windows venvでは1つのシーンがランチャー＋実Pythonの2PIDになる場合があるので、単純なPID総数とシーン数を混同しない。
- 同一シーン20回の合格は、GPUを含む異種シーン間の合格とは区別する。従来primary構成の20回完走を、Xiaomi構成の確認へ読み替えない。

### Xiaomiでの長時間運転・12時間

本番候補のリスト・Acer／Xiaomiの拡張表示・実行環境を固定し、同じ基準を12時間維持する。観客映像がXiaomiの観客用拡張ディスプレイで継続し、DISPLAY1で運用管理できることも確認する。途中の人の操作、無人区間、USB／電源／DPI、温度／GPUメモリを時刻付きで残す。再起動した場合は「12時間再起動なし」を合格にしない。単一30分・切替反復・USB復帰と長時間試験の結果は別々に記録し、自動テストをこの耐久試験の代わりにしない。

## 旧Mac/PAN検証の履歴

以前はMacからの操作とネットワーク疎通を確認項目に含めた。カメラなし疎通入口・Acer内のHTTP成功・Mac実通信未確認という記録は [継続検証記録](WINDOWS_VENV_RUNTIME_CHECK_20260906.md) と [OPERATOR_PANEL.md](OPERATOR_PANEL.md) の履歴へ保持する。現在はMacを本番対象外とし、Bluetooth PANとMac–Acerネットワークの追加調査・設定変更・試験は行わない。Mac接続をAcer単体試験の開始条件や合格条件にしない。

## 失敗時

Manager ControlのqまたはコンソールCtrl+Cで通常終了する。関連ファイル一式、失敗時刻、最後のscene_control、試験条件、実際の画面、最後のsampleを保存する。Job停止やカメラjoinが未完了なら、そのPIDを確認してから人間が該当アプリだけを終了する。別ディレクトリのシーンやTouchDesignerまで一括終了しない。

映像ウィンドウのEsc/qは子シーンだけの終了で、Managerは復帰のため同じシーンを起動し得る。全体を終える場合は操作UIの「Managerを終了」またはManager Controlのqを使う。無中断試験中のNext、n、Esc/qは時刻と対象ウィンドウを記録し、無操作の試験結果と区別する。

最初の再確認順は **finger_colorfull_dots_acer → finger_grid_interaction_acer → particle_storm_acer**。それぞれ、映像と指先の入口、Pygame側の複数手/CPU負荷、WGPU/モデル/描画資源の経路を段階的に確かめるため。これは本番採用の決定ではない。
