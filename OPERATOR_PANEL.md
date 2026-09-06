# AcerのローカルUIで露出・ズームを調整する

Acer Windows 11のDISPLAY1に操作ブラウザとManager Controlを置き、Xiaomiの観客用拡張ディスプレイ2（OS内部名DISPLAY5）へ観客映像だけを全面表示する。Acer上のManagerへローカルブラウザから設定を送り、Xiaomiの映像とカメラの読戻し値を確認してからJSONへ保存する。物理C922n USBカメラを所有するのはManagerだけで、ブラウザはカメラを直接開かない。このUIへ映像・顔・手のデータは送信しない。

**現行方針ではMacを本番対象外とし、Bluetooth PANとMac–Acer間のネットワーク検証は中止。追加調査・設定変更は行わない。** 過去のMac/PAN試験は末尾へ履歴として残す。

従来構成ではAcer内のブラウザから、実C922nへの露出・ズーム適用、読戻し、元の値への復元、プレビューJSON保存、シーン切替、Manager終了を確認した。結果は [CAMERA_RUNTIME_CHECK_20260906.md](CAMERA_RUNTIME_CHECK_20260906.md) に記録した。新しいXiaomi向け入口・2画面配置・DPIを含む実機確認は未完了である。

露出は会場の照明に合わせてDISPLAY1のAcerローカルUIから調整する。暗い部屋でのFPSの追加追究は後回しとし、FPSだけで値を決めず、Xiaomi上の明るさ・残像・操作の分かりやすさを見てから保存する。

## DISPLAY1で操作UIを開く

既存の映像用Pythonを同じPowerShellで指定し、Xiaomi向け候補を起動する。環境選択と2画面の前提は [KIDS_TEST_START.md](KIDS_TEST_START.md) を参照。

```powershell
Set-Location -LiteralPath 'C:\Users\go\Documents\ChatGPT\New project'
$env:KIDZDISCO_PYTHON = 'C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe'
& '.\Start Rebirth Acer.cmd' --check
& '.\Start Rebirth Acer.cmd'
```

新しい入口は `scripts/start_kids_test.py --audience` と `configs/rebirth_acer_xiaomi.json` を使う。`--check` は依存と2画面を読み取り、カメラ・ウィンドウを開かない。OS名 `\\.\DISPLAY1` がprimary、観客側の `\\.\DISPLAY5` がnon-primaryかつ互いに重ならない拡張領域であることをカメラ取得前に検証する。条件不一致や第2画面不在では終了コード2で止まり、primaryへ自動的に出し直さない。

XiaomiはHDMI接続後の実読で内部名DISPLAY5、EDID名 `Mi TV(XMD)` と確認し、新しいaudience preflightは成功した。用途上の「2枚目」とWindowsの内部番号は別である。ポート等を変更した場合は `--check` の検出名と設定JSONを再照合する。実映像・DPI・UI操作の新構成での合格は未確認のまま扱う。

起動ログの `[Operator]` 行にある操作URLを、`#token=` 以降も含めて**DISPLAY1のAcerブラウザ**で開く。audienceモードのhostは `127.0.0.1` に限定され、他hostは拒否する。既定ポートは `8766`。HTMLファイルを直接開くのではなく、起動ログのURLを使う。Manager ControlもDISPLAY1座標へ明示配置する。

操作URLのトークンはManagerの起動ごとに変わる。ブラウザが同じトークンをBearer認証に使うため、古いURLでは操作できない。トークン付きURLをリポジトリや共有の記録へ保存しない。

別のTouchDesigner/BridgeやPythonがC922nを使用している場合は、その作業を保存し、通常終了してカメラを解放してからManagerを起動する。別作業のプロセスを一括強制終了しない。

従来の `Start Kids Test.cmd` は `configs/kids_test_acer.json` とprimary画面による机上確認用として残る。Xiaomi向け入口の検証失敗時に自動で使うものではなく、机上確認を明示的に行う場合の入口である。

## 適用してから保存する

|操作|結果|
|---|---|
|露出・ズームの値を編集|入力欄だけ変わる。まだ映像・JSONは変わらない|
|「映像に適用」|チェックした項目をManagerへ送る。カメラを取得している処理が設定し、読戻し値を照合する|
|「適用済みの値をJSON保存」|直近の適用成功を確認できる場合に、その起動中に適用成功した項目を起動時の設定JSONへ保存する|
|「次のシーンへ」|Managerへ切替を要求する。現在の子供向け試験設定は1シーンなので同じシーンを起動し直す|
|「Managerを終了」|確認ダイアログの後、Manager・子シーン・カメラ・操作UIの通常終了を要求する|

1. 変更前の入力値と「実際の値」を記録する。値を変えない項目は「この値を適用する」のチェックを外す。
2. 少しずつ変更し、「映像に適用」を押す。「反映中」が終わり、成功表示と「実際の値」を確認する。
3. Xiaomiの観客映像で明るさ、動きの残像、遅延、手や体が画角から切れないことを確認する。ズーム変更後は中央と四隅で指先と反応が重なることを再確認する。操作ブラウザとManager ControlはDISPLAY1で扱う。
4. 採用する値になったら「適用済みの値をJSON保存」を押す。保存先は起動時の設定JSONで、Xiaomi向け入口では `configs/rebirth_acer_xiaomi.json`、従来の机上確認入口では `configs/kids_test_acer.json`。ログと起動入口を照合してから保存する。カメラ以外の設定は保持する。
5. 通常終了して同じ設定で再起動し、起動ログ・読戻し・映像の3点で保存した値を確認する。

保存されるのは `CAMERA_EXPOSURE` と `CAMERA_ZOOM` のうち適用成功した項目。まだ適用していない入力値、適用に失敗した値は保存しない。保存ボタンはその起動中に成功した設定を累積して保存するので、前の調整で適用した項目も対象になる。

|項目|UI入力範囲|留意点|
|---|---|---|
|露出|整数 `-13` ～ `0`|カメラの露出プロパティ値。秒数ではない。明るさと動きの見え方を一緒に確認する|
|ズーム|整数 `100` ～ `500`|カメラのズームプロパティ値。対応する刻みは機器・ドライバーで確認する|

この範囲は**アプリの入力制限**であり、C922nの全値・全刻みの対応を保証するものではない。「実際の値 取得不可」は読取に失敗したか、アプリの範囲外の値だったことを示す。その項目を外して他の項目を試せる。拒否や読戻し不一致は設定エラーとして表示し、変更前の値への復元を試みる。復元未確認の表示が出た場合は、元に戻ったと判断せず映像と値を確認する。

「実際の値」は起動・再接続・設定適用時の読戻しであり、UIの毎秒更新でドライバーを再読取しているわけではない。自動露出モードや後からの機器側変更をこの表示だけで判定しない。

JSONは次回起動時に読み込む。起動中にJSONを手動編集しても即時反映しない。`KIDZDISCO_CAMERA_EXPOSURE` / `KIDZDISCO_CAMERA_ZOOM` が環境変数にある場合は起動時にJSONより優先されるので、保存値と違う場合は起動ログの設定元も確認する。

## 元へ戻す・失敗を記録する

保存前なら、記録した変更前の値をUIから適用する。保存後なら、変更前の値を適用・確認して再度JSON保存する。起動できなくなった場合はManagerを停止してから、実際に使用したJSONの該当2項目を以前の値へ戻して再起動する。従来のprimary机上確認でUIだけを無効にする場合は `Start Kids Test.cmd --no-ui` を使う。

保存せず終了しても、ドライバーによっては設定値がカメラに残る。JSONを `null` にするだけでは機器の値は復元しないため、復元したい値を明示して確認する。

失敗時は、試験ID、変更前・要求・読戻し値、UIのエラー全文、`[CameraControls]` 行、Camera diagnostic、終了理由・PID、USB接続と画面条件を残す。JSON保存失敗時はファイルの保存先と書込可否、他の編集との競合も確認する。記録に操作トークンやカメラ画像を含めない。

## 2画面構成で必要な人間の確認

DISPLAY1の操作UIとManager Control、Xiaomiの観客用拡張ディスプレイ2（現在の内部名DISPLAY5）の観客映像を実際に照合する。DPI・倍率・座標、露出／ズーム適用後と保存値での再起動後の5点一致、操作中も観客画面へ管理画面が出ないことは未確認。ディスプレイ切断時にOSがウィンドウを別画面へ移す挙動も未確認で、起動前の画面検証だけでは合格にしない。単一30分、切替反復、USB復帰、Xiaomi長時間運転は [ENDURANCE_TEST_PLAN.md](ENDURANCE_TEST_PLAN.md) で別々に記録する。

## 旧Mac/PAN方針の履歴（現在の実行対象外）

以前はAcerホットスポット／Bluetooth PAN／同じWi-Fiを候補とし、Macのブラウザから露出・ズームを調整する方針だった。旧手順では選んだ接続のAcer側IPv4を `--operator-host` へ指定し、別に `Check Mac Connection.cmd` のカメラなし疎通入口を用意した。これは現行audienceモードのローカルhost制限とは異なる旧方式である。

旧疎通入口は既定8767番・10分で自動終了し、別途30分の待受も行った。接続記録は `test_reports/mac_connection_*.jsonl`。Acer自身からのHTTP成功をMac通信の合格へ読み替えておらず、Macからの実通信は未確認のまま中止した。試験IDと観測は [WINDOWS_VENV_RUNTIME_CHECK_20260906.md](WINDOWS_VENV_RUNTIME_CHECK_20260906.md) に保持する。トークンや一時URLを共有資料へ保存しない扱いも維持する。

最新のユーザー方針により、Macは本番対象外で、Bluetooth PANおよびMac–Acerネットワークの追加調査・設定変更・疎通試験は行わない。この履歴を、接続準備を再開する手順や現在の合格条件として扱わない。
