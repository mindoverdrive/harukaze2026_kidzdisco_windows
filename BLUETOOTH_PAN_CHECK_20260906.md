# Acer / M1 Mac の Bluetooth PAN 実機確認

2026-09-06。基準点は `705b081`、候補ブランチは `codex/rebirth2026-production-candidate`。

**最終観測（13:31 JST）：Bluetoothペアリングは成功したが、PANは未成立。Macのネットワーク一覧とサービス追加候補の両方にBluetooth PANがなく、ここで検証を停止する。** MacはTahoe 26.6.2との申告。PAN経由のIP・双方向疎通・HTTP・SSH・再接続・短時間安定性は合格していない。構成変更や別方式の採用へ自動で進まない。

Mac側の既存一覧はWi-Fi・VPN・ファイアウォール・Thunderbolt Bridge・iPhone USBとのユーザー報告。続いて「サービスを追加」のインターフェイス候補はThunderbolt Bridge・Wi-Fi・PPPoE・6to4で、チェックはThunderbolt Bridgeに付いているとの報告を受けた（音声の「PPPOE624」はPPPoE / 6to4として整理）。Bluetooth PANの追加候補を確認できない。Thunderbolt BridgeをPANとして作成せず、現在のダイアログはキャンセルで閉じる案内とする。

13:31:48のAcer再読取でもPANはDisconnected、IPv4はTentative、TCP 22/8767の待受なし、sshdはStopped。現在の標準UIでPANの接続経路を用意できる状態を確認できないことが停止理由である。内部の非対応原因を特定したわけではなく、macOS全般の非対応やBluetooth故障とは断定しない。

ユーザーから、Mac側でペアリング成功・接続済み表示、両機のVPNオフとの更新を受領。Acer側でもペアリング成功ダイアログと登録デバイスを確認した。13:24:37の実機読取では、PANアダプターとIPインターフェースはともにDisconnected、169.254系IPv4はTentative、有効なPANのユニキャスト経路はない。UpのアダプターはWi-Fiだけであり、Bluetoothデバイスとしての接続をPAN成功とは扱わない。PANのIP割当・双方向疎通・HTTPの検証前である。

**13:14 JST追記:** ユーザーから「Tahoe 26.6.2、見えてない」と回答を受領。OS版は申告値として記録し、直前の確認質問に対してAcerの機器一覧にMacが表示されないとの回答として扱う。Acerの再読取でもPANはDisconnected、BluetoothサービスはRunning。PANプロファイル非対応とは断定せず、逆方向としてMacのBluetooth設定「近くのデバイス」にAcer名 `AYM_ILL` が表示されるかを追加確認した。

その後ユーザーが、Mac側では `AYM_ILL` が表示されると回答した。**Mac→Acerの機器検出はユーザー確認済み**。Windows設定を前面で再取得すると「デバイスを追加する」の種類選択画面であり、Acer側の実スキャンが完了した証拠はまだない。従って最初の「見えない」だけを無線の検出失敗とは断定しない。Macから「接続」を押し、両機の番号を照合してペアリングできるか、ユーザーへ操作と結果の確認を依頼した。ペアリングとPAN成立は分けて記録する。

## 今回の優先変更

ユーザーから、接続方式に依存しないコード作業よりBluetooth PANの実機確認を優先する指示を受けた。成立しない場合は原因・制約を記録して報告し、大きな構成変更・機材購入・他の接続方式の採用へ進まない。

`705b081`に至る両Python環境120テスト、C922nの正常交代20回、同試験中の取得失敗・再接続試行・終了後所有資源残留0は過去の証拠として維持する。無中断30分、実映像・子供・複数人、Xiaomi、実USB復帰、12時間試験は引き続きHuman Check Required。試験中の再接続試行0は実USB再接続の成功を意味しない。

## 実機で読み取った事実

|項目|観測|判定|
|---|---|---|
|Acer OS|Windows 11 Home / 10.0.26200|実機読取済み|
|Bluetooth|Intel Wireless Bluetooth、サービス稼働、設定画面でオン|無線機能あり|
|PANアダプター|Bluetooth Device (Personal Area Network)、ifIndex 8、Disconnected|PAN接続未成立|
|PAN IPv4|169.254系の値はあるがインターフェース未接続|IP通信成功の証拠にしない|
|Macペアリング|初回は記録なし。13:24にはMac側の成功申告、Windows側の成功ダイアログとデバイス登録を確認|Bluetoothペアリング成功、PANとは別|
|既存HTTP|Wi-Fi側の明示IPv4、TCP 8767、PID 30328で待受|PANインターフェースの待受ではない|
|Acer内HTTP|13:04:31 JST、既存URLへ直接GET、200 / 651 bytes|サーバー自己確認のみ|
|HTTPアクセス記録|13:09時点の2件は両方Acer自身のIP|Mac到達の記録なし|
|SSH|OpenSSH Serverインストールあり、sshdはStopped / Manual、TCP 22 listenerなし|SSH試験未開始|
|Mac OS / PAN機能|M1・Tahoe 26.6.2（ユーザー申告）。既存ネットワーク一覧とサービス追加の候補にBluetooth PANなし|現行標準UIでの手順を停止。PAN実通信未確認|

13:11:29 JSTの再読取で既存待受の予定終了を確認した。ログは「時間制限」で終了し、PID 30328とTCP 8767 listenerは存在しない。アクセスはAcer自身の2件のみ。ページの期限終了を接続失敗と数えない。

Wi-Fi経由のMac HTTP未成功は維持するが、URL入力・待受IP・OS設定などの原因をまだ切り分けていない。Wi-Fi障害とは断定しない。Wi-Fiの自己HTTP成功からBluetoothの通信可否も推定しない。

## 操作できた範囲と制約

WindowsのBluetooth設定を開き、「デバイスを追加する」ダイアログまで進めた。次の「Bluetooth」選択は、操作ツールが `ShellExperienceHost.exe` のダイアログを `SystemSettings.exe` のクリック対象として受け付けず失敗。画面を再取得して1回再試行したが同じ拒否だった。ペアリング要求は送信していない。

これはUI操作ツールの対象ウィンドウ制約であり、Bluetoothドライバー故障、OSの権限拒否、PAN非対応の証明ではない。Mac側を直接操作する接続もないため、ユーザーへOS版・PAN項目・デバイス検出の確認を依頼した。

Codexは固定IP、VPN、Firewall、SSH設定、共有設定、ドライバー、Python環境、カメラ、シーンを変更していない。ユーザーが両機のVPNをオフにし、Bluetoothペアリング操作を実施した。HTML作業にも触れていない。

## 公式資料と、その限界

Windowsの公式接続手順は、相手にBluetooth共有機能があり、ペアリング後にWindowsからPANへ参加する構成を説明している。ペアリングだけでIP通信が成立するとは扱わない。[Microsoft: Bluetoothネットワークへの接続](https://support.microsoft.com/en-us/windows/hardware/bluetooth/connect-to-a-bluetooth-network-in-windows)

WindowsのMobile hotspot資料にはBluetooth経由の共有が記載されている。ただし、このAcerの設定画面で共有先として選択可能かは未確認。[Microsoft: Mobile hotspot](https://support.microsoft.com/en-us/windows/experience/connectivity-networking/use-your-windows-device-as-a-mobile-hotspot)

Appleの現行手順にはiPhoneとMacのBluetooth経由テザリングが記載されているが、Windowsと当該M1 Macの組み合わせを保証する記述ではない。[Apple: iPhone/iPadの接続共有](https://support.apple.com/guide/mac-help/iphone-internet-connection-mac-mchl7403f0ee/mac)

macOS Tahoe 26のInternet Sharing説明だけでは、当該MacにBluetooth PANの共有先やネットワーク項目があるか確定できない。正確な版番号と実機表示で判断する。[Apple: MacのInternet Sharing](https://support.apple.com/en-my/guide/mac-help/mchlp1540/26/mac/26)

Macのサービス追加はApple公式の「アクション→サービスを追加→インターフェイス」の手順で候補を確認した。候補一覧の実機報告は上記のとおりで、サービスの作成は指示していない。[Apple: ネットワークサービスを設定する](https://support.apple.com/ja-jp/guide/mac-help/mchlp1176/mac)

## 保留と再開条件

ペアリングは完了済み。未達はPANのネットワーク接続であり、同じペアリングを無制限に繰り返さない。Mac側のBluetooth PANを提供・接続できる具体的な標準機能の手順が確認できた場合、その箇所から再開する。AcerをBluetooth共有側にする操作、MacのCLIでのインターフェイス列挙や作成、ドライバー変更などは今回実施しておらず、全方式を否定した結果とはしない。購入や別の本番接続方式は未決定のまま。

再開できた場合に限り、PANのUp状態・両端IP・経路、双方向の到達、既存の接続確認用プログラムをPAN実IPへ明示bindしたHTTPの順で確認する。元の待受はWi-FiのIP限定なので、そのURLをPAN成功の根拠にしない。HTTP後にSSH、PAN切断→再接続、5分程度のHTTP失敗数・遅延・PAN状態・SSH維持を記録する。既存Wi-Fi経由の成功が混ざらないよう両端の経路と到達元を照合する。

上記は未実施の次手順であり、合格記録ではない。169.254系のみの場合、既存HTTPプログラムはRFC1918/loopback以外を拒否する。その場合も勝手に全インターフェース公開やコード変更へ進まず、PAN/IP成立の証拠とこの制約を先に整理する。

## 証拠とロールバック

ローカル証拠はGit対象外の `test_reports/` に保持する。操作URLのランダム文字列や機器識別子を共有文書へ転記しない。

- `pan_acer_baseline_20260906.json`: 13:03のOS・アダプター・IP・サービス・待受。
- `pan_services_20260906.json`: ペアリング名の検索、PANインターフェース、SSHサービス。
- `pan_existing_http_selfcheck_20260906.json`: 既存URLのAcer自己HTTP検査。
- `pan_before_handoff_20260906.json`: 13:09のPAN・待受・HTTP記録。
- `pan_probe_final_20260906.json`: 13:11の未接続、待受の期限終了とPID/port解放。
- `pan_acer_after_mac_report_20260906.json`: Mac側情報を受領した13:14のPAN・Bluetooth・SSHサービス再読取。
- `pan_after_pairing_20260906.json`: 13:24のペアリング後PAN状態・IPv4・経路・デバイス登録・有効アダプター・待受。機器識別子を含むためGit対象外。
- `pan_no_mac_interface_20260906.json`: Macの追加候補にPANがないとの報告後、13:31のAcerのPAN・IPv4・SSH・HTTP待受を再確認。
- `mac_link_standby_20260906_1210.jsonl`: 自己アクセスを含む既存待受の記録。予定終了は13:10:47 JST。

コード・設定の基準点は `705b081` のまま。接続診断では戻すべきネットワーク設定変更はない。後続の文書コミットは履歴を消さずrevertできる。

優先変更前のrunner終了処理の赤い回帰テストは、未実装の作業として `test_reports/paused_runner_finalization_20260906/` へ移動前後のSHA-256一致を確認して保全済み。7テスト・11失敗は未修正の再現記録であり、新しい修正の合格記録ではない。既存testsの収集対象と製品コードへ未完の作業を混ぜず、PAN確認の保留理由とコード修正の残件を区別する。
