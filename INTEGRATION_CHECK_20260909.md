# 全シーン統合確認

基準コミット: `2a6a116cde4d829c1e46106745109aef9f5ec306`。製品コードは変更しない。

## 最終結果

### 最新: 15分完走、追加45分は予定外Backで中断

監視基準修正後の15分は900秒・38操作完了。追加45分は03:04:14開始、1589.781秒（約26分30秒）・44操作で自動試験を停止した。合計の試験実施時間は約41分30秒だが、45分完走または連続60分合格とはしない。

- 停止直前: 自動NextでSkeleton→Particle Stormを完了（経過1561.391秒）。次の自動操作前、03:30:43の既存runtimeにtransition ACTIONと `scene_request action=back target=skeleton_glitch_acer.py` が記録された。試験ドライバーには対応するBack送信がないため、予定外状態変化として停止。人間操作・手の検出・誤検出のどれかはログだけでは特定しない。
- 追加試験の完了操作: Next23、Back17、Safe/解除/Restart/直接選択各1、計44。全17シーンがNext/Backの両方向で少なくとも一周済み。2周目の残り32操作は未実施。
- カメラ失敗/再接続0、最後のswitch_errorなし、監視stderr空。初期化後基準からの新規起動プロセスprivate増加最大31.14MiB、プロセス数は開始/停止直前とも5。低処理FPSはSkeleton 7.73〜8.12、Spheres 8.03〜8.09、Wave 11.10〜21.90として残す。持続的な劣化閾値には達していないが滑らかさの目視合格とは別。
- 製品修正・自動再試験なし。停止後も本体は稼働し、別のシーンへの切替も既存ログにあるため、停止後の操作を自動試験に算入しない。
- 根拠: `test_reports/final_endurance_45m_20260909/{summary.json,events.jsonl,runtime.jsonl,analysis.json}`。製品基準は2a6a116。子供/複数人は対象外、GPUメモリ・追加試験終了後の2画面目視・見た目の状態漏れ・残り32操作は未確認。

### 追加60分試験: 未完了（監視条件で停止）

### 監視修正後の15分再試験

製品コードを変更せず、監視の基準をFIRST_FRAME+5秒後の初回メモリ観測へ変更。初期化除外・後続増加の保持・再起動識別の3テスト成功。試験補助の時間と間隔は900秒・20秒に設定。

2026-09-09 02:43:06開始、900.000秒完走。Next17、Back17、Safe/解除/Restart/直接選択各1、計38操作完了。カメラ取得失敗/再接続0、終了状態Prism / busy=false / covered=false / safe=false / error=null、stderr空。

新規起動プロセスでFIRST_FRAME後に採用した基準からの最大private増加は20.03MiB。管理下プロセス数は開始・終了とも5。processed_render_fpsはシーン差がありSkeleton約7.91〜8.06、Spheres約8.05〜8.12、Wave約13.99〜16.47など低い値も記録。これだけで実表示の滑らかさを合格としない。監視閾値に該当する持続的FPS低下・メモリ増加はなし。根拠 `test_reports/final_endurance_15m_20260909/analysis.json` と同ディレクトリの生ログ。

重大な監視異常がないため、同じ製品・設定で追加45分（2700秒、約35秒間隔、全方向2周と運営操作）へ進める。2画面の目視・無人中の見た目の状態漏れは自動判定しない。子供・複数人は対象外。

2026-09-09 02:07:27開始の追加試験は180.187秒で自動操作を停止。60分合格ではない。既存の30分試験合格を取り消す結果でもない。製品は変更せず、Sci-Fi Jacketの表示を維持。

- 操作順: Fractal → NextでMandala → Wave Dots → Tree → Sci-Fi Jacket。約45秒間隔。4回のNextは完了し、Jacket FIRST_FRAMEは2.484秒。Back、Safe/解除、Restart、直接選択はこの追加試験では未到達。
- 停止原因: 試験補助スクリプトがPID9572の生成直後のprivate bytes 10,330,112を基準に採用し、描画開始後732,643,328→738,201,600→756,719,616が3サンプル連続で512MiB増の条件を超えた。つまり監視条件が初期化前後の増加を異常と判定したことは確定。製品のメモリリークは確定していない。
- 停止後の既存ログを読むと02:15:48〜02:16:08は782,610,432→789,843,968→767,045,632 bytesと上下している。handles=702、GDI=24、USER=20。約6分の情報のみで長時間リークなしとは断定しない。
- Jacket processed_render_fpsは02:16頃までの37サンプルで16.92〜46.2。末尾は17.7、28.71、16.97、17.35、17.6。描画負荷は観測されたが、視覚的な重さや一方向の劣化は今回未判定。
- カメラ取得失敗・再接続は0、switch_error=null、監視stderr空。試験の自動操作だけを停止し、製品修正・自動再試験は行わない。
- 次回の試験方法案: 製品ではなく監視の基準点をFIRST_FRAME後の一定時間に置き、同じ起動内の安定後傾向と同じシーンの周回間差を比較する。今回は案に留める。
- 根拠: `test_reports/final_endurance_60m_20260909/summary.json`、`events.jsonl`、`runtime.jsonl`、既存`test_reports/operator_20260909_004844/runtime.jsonl`と`scene_output.jsonl`。製品基準2a6a116、前回合格記録c680b43。
- 子供・実際の複数人試験は今回対象外。60分全体、追加試験の後半操作、GPUメモリ、無人中の映像の状態漏れは未確認。

前回c680b43の範囲は合格。全17シーンの統合目視確認、30分・34回（2周）の自動切替、Acer操作画面とXiaomi拡張表示、本番想定のSafe/解除・Restart・一覧直接選択を確認した。以下の「次」「結果待ち」は経過記録であり、後続の結果を優先する。

製品基準は引き続き `2a6a116`。今回保存する変更はこの検証記録のみ。自動切替試験は終了し、Fractal Movingを表示したままにしている。

未確認・保留は、12時間連続運転、GPUメモリ推移、子供自身による操作、実際の複数人同時操作（両手確認とは別）、現場の照明・設置距離での検出品質。過去の単発アクセス拒否は今回再現していないが、原因解決済みとは扱わない。終了→再起動やUSB抜き差しは今回の試験では実施していない。

再開は既存 `scripts/start_operator.py` を本番Python環境で実行する。現在は起動中なので重複起動しない。製品ロールバック基準は `2a6a116` のままで、今回の文書コミットは実行挙動を変更しない。

## 確認済み

- 最初の Fractal → Mandala → Wave Dots → Mandala の往復確認にユーザーが「ok」と回答。
- `test_reports/integration_20260909.stdout.log` に各起動の FIRST_FRAME と切替を確認。
- 追加でログ上は Mandala → Fractal → Living Mosaic → Fractal の境界往復も記録。これは全17シーンの目視合格を意味しない。

## 次の確認

- Wave Dots → Tree → Sci-Fi Jacket → Tree の表示・反応・切替のつながりはユーザーが「ok」と回答。各 FIRST_FRAME をログで確認、API は Tree / busy=false / error=null。確認時の stderr は空。
- 次は Sci-Fi Jacket → Skeleton Glitch → Particle Storm → Skeleton Glitch の接続確認。Skeleton は黒背景が正しい仕様。
- 上記の依頼にユーザーは「ok」と回答。ただし今回のログは Jacket → Skeleton → Jacket → Skeleton で、Particle Storm の起動記録はまだない。Jacket/Skeleton の目視OKとして受領し、Storm往復は未確認のまま再提示する。API は Skeleton / busy=false / error=null、確認時 stderr は空。
- 再提示後、Skeleton → Particle Storm → Skeleton にユーザーが「ok」と回答。ログでも往復の FIRST_FRAME を確認（Storm 6.281秒、Skeleton 2.735秒）。API は Skeleton / busy=false / error=null、stderr は空。Storm往復の未確認を解消。製品コードは変更なし。
- 次の目視確認は Particle Storm → Colorful Dots Spheres → Finger Colorful Dots → Colorful Dots Spheres。
- 上記への「ok」はログ上の Storm → Spheres → Storm の往復として記録。Spheres FIRST_FRAME 3.094秒、Storm 5.250秒、APIはStorm / busy=false / error=null、stderr空。Finger Colorful Dots の起動記録はなく、未確認。次はSpheresを直接表示してFinger Colorful Dotsとの一往復だけを依頼する。
- 一往復の再提示後、Spheres → Finger Colorful Dots → Spheres にユーザーが「ok」と回答。ログの FIRST_FRAME は Finger Colorful Dots 2.406秒、戻りのSpheres 3.156秒。API は Spheres / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は Finger Colorful Dots → Spider → Finger Colorful Dots の一往復。
- Finger Colorful Dots → Spider → Finger Colorful Dots にユーザーが「ok」と回答。ログの FIRST_FRAME は Spider 2.703秒、戻りのDots 2.500秒。APIはDots / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は Spider → Finger Grid Interaction → Spider の一往復。
- Spider → Finger Grid Interaction → Spider にユーザーが「ok」と回答。FIRST_FRAME は Grid 2.516秒、戻りのSpider 2.422秒。APIはSpider / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は Finger Grid Interaction → Saturn → Finger Grid Interaction の一往復。
- Grid → Saturn → Grid にユーザーが「ok」と回答（指先とカーソルの一致・粒子反応・復帰・タスクバー非表示を含む依頼）。FIRST_FRAME は Saturn 5.344秒、戻りのGrid 2.453秒。APIはGrid / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は Saturn → Prism Skin → Saturn の一往復。
- Saturn → Prism Skin → Saturn にユーザーが「ok」と回答。FIRST_FRAME は Prism 2.532秒、戻りのSaturn 5.234秒。APIはSaturn / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は Prism Skin → Polygon Vibes → Prism Skin の一往復。
- Prism Skin → Polygon Vibes → Prism Skin にユーザーが「ok」と回答。FIRST_FRAME は Polygon 2.531秒、戻りのPrism 2.485秒。APIはPrism / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は Polygon Vibes → Kaleidoscope Camera → Polygon Vibes の一往復。
- Polygon Vibes → Kaleidoscope Camera → Polygon Vibes にユーザーが「ok」と回答。FIRST_FRAME は万華鏡 1.641秒、戻りのPolygon 2.515秒。APIはPolygon / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は Kaleidoscope Camera → Polygon Face → Kaleidoscope Camera の一往復。
- 万華鏡 → 顔Polygon → 万華鏡 にユーザーが「ok」と回答。FIRST_FRAME は顔Polygon 2.437秒、戻りの万華鏡 1.625秒。APIは万華鏡 / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は Polygon Face → Living Mosaic → Polygon Face の一往復。
- 顔Polygon → Living Mosaic → 顔Polygon にユーザーが「ok」と回答。FIRST_FRAME は Mosaic 1.672秒、戻りの顔Polygon 2.375秒。APIは顔Polygon / busy=false / error=null、stderr空。今回の接続確認は合格。
- 次は最終シーン Living Mosaic → 先頭 Fractal Moving → Living Mosaic の境界往復を目視確認する。
- 最終Mosaic → 先頭Fractal → 最終Mosaic にユーザーが「ok」と回答。FIRST_FRAME はFractal 2.422秒、戻りのMosaic 1.641秒。APIはMosaic / busy=false / error=null、stderr空。境界往復の目視確認は合格。

## 統合目視確認の到達点

全17シーンが今回の目視確認に登場し、映像・各シーンの反応・切替後の復帰・タスクバー非表示についてユーザーがOKと回答。各組の範囲とログ照合は上記参照。長時間安定性、全ての操作組合せ、子供確認、実際の複数人操作まで合格と拡張しない。

次段階は製品コード・カメラ設定を変えず、稼働中の既存APIで約50秒ごとにNextを送り、30分の切替反復とプロセス資源を記録する。これは12時間耐久試験ではない。異常時は自動切替を止め、状態を残す。

## 30分切替反復の結果

- 2026-09-09 01:19:02開始、1801.266秒で完走。既存Next APIで34回、全17シーンを各2回切替完了。終了時Mosaic / busy=false / covered=false / error=null。
- 323回の資源観測。Manager private bytes 666656768→666771456（約0.11MiB増）、handles 853→764、範囲763〜855。管理下Pythonプロセス数は開始5・終了5・切替中最大7。今回の範囲で継続的な蓄積を示す結果はないが、リーク不存在や12時間安定を断定しない。
- 既存runtimeログの該当180サンプルではカメラread_failures/reopen_attemptsは開始・終了とも0、last_error=null。累積max_frame_gap_sは0.203のまま。stdoutのfailed/Error/Traceback/timeout検索該当なし、stderr空。
- 切替完了の観測最長10.719秒は約5秒間隔のポーリングを含む値であり、正確な描画遅延ではない。GPUメモリは既存ログでnullのため未評価。
- 監視補助スクリプト初回はpsutil未導入で開始前に停止。環境や製品を変更せずWindows標準計測へ置換して上記試験を実施。
- 根拠: `test_reports/integration_endurance_20260909/{summary.json,observations.jsonl,analysis.json}`、`test_reports/operator_20260909_004844/runtime.jsonl`。自動切替は完了して停止、本体Mosaic表示は維持。

## 本番ディスプレイ構成確認

- 列挙結果: 操作用DISPLAY1は1920×1080・主画面・(0,0)、観客用DISPLAY5は1920×1080・拡張・(1920,0)。設定との一致を確認。
- 次の人間確認: Acerの操作画面をクリックしてもXiaomiのMosaic表示・動きが継続し、タスクバーや操作画面が観客側へ出ないこと。これは結果待ち。本番想定通し試験も未完了。
- 上記2画面確認にユーザーが「ok」と回答。操作画面クリック後の観客表示継続・全面表示・タスクバー非表示を合格として記録。確認後APIはMosaic / busy=false / safe=false / covered=false / error=null。
- 本番想定操作の次項目は、既存オペレーターUIの「Safe · 演出遮蔽」→「Safe解除」で観客映像を隠して同じシーンへ復帰できるか。結果待ち。
- Safe遮蔽→5秒保持→Safe解除にユーザーが「ok」と回答。APIはMosaic / busy=false / safe=false / covered=false / error=null、feedback=resume受付済み。遮蔽中の見え方はユーザー確認に基づく。stderr空。
- 次は操作パネルのRestartを1回押し、同じMosaicが既存トランジション経由で再起動し、映像・動きが復帰することを目視確認する。実行前Mosaicのscene PID=16752、launcher PID=28584、launch_id=2951e31313e14fdfabf5c78d92882471。
- Restartにユーザーが「ok」と回答。新Mosaic scene PID=22296 / launcher=24948 / launch_id=7458997310a04314a1a18eef04d560df、FIRST_FRAME 1.640秒。APIはMosaic / busy=false / safe=false / covered=false / error=null、feedback=restart受付済み。旧PID16752・28584はGet-Processで存在しないことを確認。stderr空。再起動と復帰を合格として記録。
- 次の本番想定操作は一覧の「fractal moving」を直接選択し、復帰後に手を動かす確認。ユーザーによるUI直接選択の見え方は結果待ち。
- 一覧直接選択にユーザーが「ok」と回答。APIはFractal / next=Mandala / busy=false / safe=false / covered=false / error=null、feedback=select受付済み。FractalのFIRST_FRAME 2.515秒、scene PID=11188 / launcher=23940。表示・反応・パネル現在表示の一致・タスクバー非表示について今回の確認は合格。stderr空。
- 残るシーンの統合確認、長時間安定性、本番ディスプレイ構成、本番想定通し試験は未完了。
- 子供による確認と実際の複数人操作は別項目として保留。
