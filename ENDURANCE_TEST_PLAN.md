# Acer / C922 基礎試験と12時間試験の準備

この文書は試験手順。実際の30分、実USBの復帰、12時間耐久は未実施。実地テスト入口は [KIDS_TEST_START.md](KIDS_TEST_START.md)。最初の候補は `finger_colorfull_dots_acer.py`。

## 実施順

1. 既存映像用Pythonで `Start Kids Test.cmd --check` を実行して依存を確認する。別のカメラ利用アプリを保存・通常終了してから候補を起動する。
2. Acerの画面で中央と四隅の映像/指先一致、一人→二人→退出→再入場を確認する。最初は大人が5分、その後子供に遊んでもらう。
3. 30分の単一シーン。意図的な切替やUSB抜去を混ぜない。
4. 同一シーンの切替を20回。Managerと共有メモリ名を維持したまま、稼働シーンのJob/PIDだけが交代するか確認する。
5. 大人がUSB切断/再接続と終了→再起動を別試験で確認する。
6. 選定済みの異なるシーン間を確認し、基本試験の合格を人間が記録してから12時間へ進む。

## コマンド

以下はリポジトリのPowerShellから実行する。`KIDZDISCO_PYTHON` の選択方法はKIDS_TEST_START.mdを参照。

```powershell
# 30分の単一シーン。最初のFIRST_FRAME後から計時し、通常の終了処理へ進む。
& '.\Start Kids Test.cmd' --duration-minutes 30

# 同じ基準シーンを20回切替。20秒ずつ見て、最大30分で終了する。
& '.\Start Kids Test.cmd' --switch-every 20 --switch-count 20 --duration-minutes 30

# 基礎合格を記録した後だけ実行する12時間試験。今回まだ実行していない。
& '.\Start Kids Test.cmd' --duration-minutes 720
```

通常configで試す場合の例（表示位置と候補リストを実機確認してから）:

```powershell
python manager.py --config config.json --report-dir test_reports\chosen_scenes_run01 --switch-interval-seconds 60 --switch-count 20
```

既存のmetadata.jsonがあるreport-dirは再利用を拒否する。試験ごとに新しい名前を付ける。子供の操作中は意図しない自動切替を避け、まず単一シーンで試す。

## 記録されるデータ

`Start Kids Test.cmd` は `test_reports/kids_trial_<日時>_<ID>/` を作る。

- `metadata.json`: コミット、作業ツリーがdirtyか、解決済みconfig、Python。実カメラ/目視確認の初期状態はfalse。合格に自動昇格しない。
- `runtime.jsonl`: 起動制御イベント、実Python PIDとランチャーPID、共有メモリ名、10秒ごとのフレーム番号/最終成功からの経過/最大フレーム間隔、再取得回数、終了理由、切替回数。
- 同じsample内にPrivate Bytes、Working Set、累積CPU時間、ハンドル、GDI/USERオブジェクトをPID別に記録。取得できない項目はunavailable/nullで残す。PID再利用を識別するcreation_ticksも記録する。
- `scene_output.jsonl`: 子シーンのstdout/stderr。`[SceneMetrics]` はカメラ処理と描画APIが成功した呼出しの10秒平均FPS。実パネルの表示更新を測った値ではない。

各ログは5MiB×現行1ファイル＋世代3ファイルの上限。2種類合わせて約40MiB（最後のレコード分は超過し得る）。長時間の大量エラーで古いログが循環した場合、初期の測定が残っているとは限らない。metadataは別保存。子の出力は読み捨てず逐次排出し、終了済みの読取スレッドを保持し続けない。データの書込失敗は試験失敗として停止処理に進む。

GPUメモリ、温度、物理パネルの表示FPS、入力から反応までの遅延は自動取得していない。タスクマネージャー等で同じPIDとGPUエンジンを確認し、手動観測として時刻付きで記録する。撮影や人物画像の自動保存は行わない。

## 暫定合格条件

### 30分単一シーン

- 初回起動後の30分を完走し、予期しない終了・再起動・切替が0回。
- 起動後のManager PID、稼働シーンのJob内実Python PID、共有メモリ名が同じ。
- 意図的な切断を含まない試験で、2秒を越えるフレーム更新停止がない。
- 処理/描画API呼出しの10秒平均が30FPS以上であり、目視でも操作位置と反応を追える。目標60FPSとは別。
- Private Bytesの5〜10分中央値と25〜30分中央値を比較し、増加が10%または50MiBの大きい方を越えたら原因調査。閾値内でも一方向に増え続ける場合は保留。
- ハンドル、GDI/USER数、GPUメモリに継続増加がない。終了後に対象PID/画面が消え、再起動でC922を取れる。

### 20回切替

- 各回に正しいlaunch_idのFIRST_FRAMEがあり、旧シーンはそれより前に終了しない。
- 20回完走。終了理由が `switch_count_reached`、`completed_switches=20`。
- 切替ごとに物理カメラの再取得が起きず、同じ共有メモリ名を使う。
- 遷移/先読みを含むJobが定常数に戻り、終了済みPIDが積み上がらない。Windows venvでは1つのシーンがランチャー＋実Pythonの2PIDになる場合があるので、単純なPID総数とシーン数を混同しない。
- 同一シーン20回の合格は、GPUを含む異種シーン間の合格とは区別する。

### 12時間

本番候補のリスト・表示・実行環境を固定し、同じ基準を12時間維持する。途中の人の操作、無人区間、USB/電源/DPI、温度/GPUメモリを時刻付きで残す。再起動した場合は「12時間再起動なし」を合格にしない。今回の自動テストはこの耐久試験の代わりにならない。

## 失敗時

Manager ControlのqまたはコンソールCtrl+Cで通常終了する。関連ファイル一式、失敗時刻、最後のscene_control、試験条件、実際の画面、最後のsampleを保存する。Job停止やカメラjoinが未完了なら、そのPIDを確認してから人間が該当アプリだけを終了する。別ディレクトリのシーンやTouchDesignerまで一括終了しない。

最初の再確認順は **finger_colorfull_dots_acer → finger_grid_interaction_acer → particle_storm_acer**。それぞれ、映像と指先の入口、Pygame側の複数手/CPU負荷、WGPU/モデル/描画資源の経路を段階的に確かめるため。これは本番採用の決定ではない。
