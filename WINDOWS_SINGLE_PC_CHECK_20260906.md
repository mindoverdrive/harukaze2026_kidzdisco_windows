# Acer単体・Xiaomi出力への本線再開

2026-09-06。安全基準点は`705b081`、作業ブランチは`codex/rebirth2026-production-candidate`。main/stableへ統合していない。

## 最新の運用方針

ユーザー指示でBluetooth PANとMac–Acerネットワーク検証を完全中止した。以後、調査・設定変更・接続検証を行わない。Macは本番構成から外し、Acer Windows 11の1台で実行・制御・映像出力を完結させる。

操作管理はAcerの主画面、観客映像はHDMI接続のXiaomi拡張画面の全領域を使う。画面の役割とWindows内部の番号を混同しない。

## 機材の照合

| 項目 | 根拠と確認範囲 |
|---|---|
| Acer | 「rebirth2026 Sol 再開」の過去ユーザー発言ではNitro AN515-58、i7-12650H、RAM16GB、RTX 4060 Laptop 8GB＋Intel UHD。過去申告と実機再測定は別。 |
| カメラ | 本線で実取得に使用してきたC922n、Windows名`c922 Pro Stream Webcam`を維持。 |
| Xiaomi | 今回ユーザーがHDMI接続。WmiMonitorIDでメーカーXMD・名称Mi TVを読み取った。型番は今回の申告`L32M8-A2TWN`と旧発言`L32MB-A2TWN`に表記差があり、ラベル実読は未実施。 |
| 操作画面 | 実読`\\.\DISPLAY1`、primary、(0,0)、1920×1080。 |
| 観客画面 | 実読`\\.\DISPLAY5`、non-primary、(1920,0)、1920×1080。用途上の2枚目であって内部番号2ではない。 |
| 現在の出力モード | 15:10:17 JST、EnumDisplaySettingsでDISPLAY5の1920×1080・60Hz・32bit、接続GPUはRTX 4060 Laptopを確認。OS報告値でありパネル実測FPSではない。 |

機材発言の参照先は「rebirth2026 Sol 再開」(task `01a06293-b8d9-7832-b177-fcc674669de4`)のturn `01a0666f-48fa-7510-98ba-815935d07f22`、`01a0678f-92fb-7fb0-be52-e459baf8b16d`、`01a06795-94a2-7bf3-b61b-57e1466cf7c2`。旧1360×800は過去のシーン窓サイズとして扱い、Xiaomiの解像度へ継承しない。

## 実装した変更

- `scene_profile_runner.py`: 終了処理を個別に試行し、finish・control.close・signal・環境復元の一つが失敗しても残りを試す。元のシーン例外を保持し、追加失敗はexception noteへ残す。借用していたcontrol/lifecycleを復元し、借用controlは閉じない。
- `stage_display.py`・Manager・表示helper: 本番設定の2画面名とprimary状態、非重複の拡張領域をカメラ確保前に確認する。欠落・複製・不一致は終了コード2。古い固定座標や列挙順に依存せず、実測の座標・サイズを子と切替効果へ渡す。子の起動時に配置が変わっていた場合も拒否する。
- audience起動時はGUI初期化前にPer-monitor DPIを確認し、SDLの座標スケーリングを無効にする。これは物理ピクセルの座標系を揃える処理で、異なる表示倍率の実機目視に合格したことを意味しない。
- 新しい`Start Rebirth Acer.cmd`は`configs/rebirth_acer_xiaomi.json`を使用し、基準dotsの1シーンだけを起動する。旧`Start Kids Test.cmd`とprimary設定は机上確認用に保持する。
- 操作UIはaudienceモードで`127.0.0.1`に限定。Manager Controlは主画面の座標へ配置する。露出・ズーム・保存・Next・終了は既存のローカルUIを使う。カメラは引き続きManagerだけが所有する。
- preflightに実ロードモジュールの版・パスとSDL版を追加した。既存環境にpygame/pygame-ceのmetadataが共存しているため、metadataだけで実ロード版を断定しない。依存の更新・新環境への入替はしていない。

DPIの根拠は[Microsoftの設定API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext)、[SDLのDPI awareness](https://wiki.libsdl.org/SDL2/SDL_HINT_WINDOWS_DPI_AWARENESS)、[SDLの座標scaling](https://wiki.libsdl.org/SDL2/SDL_HINT_WINDOWS_DPI_SCALING)。既設定の場合のPer-monitor V1も許容し、厳密V2の保証とは記録しない。

## 検証

- 保全していた終了処理の赤テストはSHA-256一致を確認して復帰。追加条件も含め修正前11件/18失敗から11件成功。
- 観客画面の不足・誤配置は修正前4件/5失敗で再現。追加した起動順・DPI・配置共有・ローカルUI条件を含む12件が成功。
- 全回帰: Python 3.11は143件/10.547秒、既存映像venv Python 3.12.10は143件/13.721秒。ともにOK・終了コード0。
- 新audience preflightは実機で成功。`test_reports/kids_preflight_20260906_150744.json`はカメラ/ウィンドウを開かない確認で、実映像と視覚確認のフラグはfalse。
- `git diff --check`成功。旧カメラ試験の20回交代・30分の証拠は今回の変更の実機合格へ移し替えない。

回帰の記録は`test_reports/windows_single_pc_unittest_py311_20260906.txt`と`windows_single_pc_unittest_py312_20260906.txt`。ローカル証拠はGit対象外。

## 次の実機確認と保留

次は短時間の基準dotsをXiaomiへ出し、実ウィンドウの範囲・Acer側の操作窓・初回フレーム・終了後の残留を確認する。この文書作成時点では新入口の実映像は未検証。

Human Check Requiredは、Xiaomi上でのC922n実映像と指先の中央/四隅一致、DPI・見切れ、複数人・子供の操作、単一30分、Xiaomi構成の切替反復、実USB復帰、画面抜去時のOS挙動、長時間試験。12時間試験は開始していない。GPU2シーンの実配置と映像品質も未確認で、この1シーン入口の採用へ混ぜていない。

## 起動・終了・ロールバック

起動は[KIDS_TEST_START.md](KIDS_TEST_START.md)、ローカルUIは[OPERATOR_PANEL.md](OPERATOR_PANEL.md)、試験順は[ENDURANCE_TEST_PLAN.md](ENDURANCE_TEST_PLAN.md)。既存映像venvを`KIDZDISCO_PYTHON`に指定して`Start Rebirth Acer.cmd --check`、成功後に通常起動する。

停止は操作UIの「Managerを終了」、Manager Controlのq、または起動したコンソールのCtrl+C。映像側のEsc/qは同じシーンを再起動する可能性がある。

`705b081`は復帰基準として履歴上に保持する。候補変更を取り消す場合は今回のコミットを個別にrevertし、履歴の強制書換えはしない。PAN試験設定は中止前の最後の観測が共有On・省電力Offで、中止後は再読取も復元も行っていない。現在の復元指示としては扱わない。
