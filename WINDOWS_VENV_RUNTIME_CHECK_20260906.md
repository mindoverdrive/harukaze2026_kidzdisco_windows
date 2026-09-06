# Rebirth 2026：映像用venvのJob修正と実機試験の継続

**最新:** `91b3200`まで候補ブランチへ通常push済み。切替回数の追加修正後、全回帰120件がPython 3.11と映像venv 3.12.10の両方で成功した。旧版`270b315`の実30分は操作・復帰を含め正常終了し、資源残留なし。修正後の実20回切替も完走し、Esc復帰3回を成功回数から除外できた。30分無中断・目視・Mac通信は未合格。

`d2864f1`の候補準備後、ユーザーの「継続」を受けて実行環境を広げて再確認した。TD終了と、新しい環境を作成してよいという指示も受領。この継続では既存の映像用venvを使用し、環境の作り直し・パッケージ更新は行っていない。

## 修正と証拠

|コミット|変更|根拠|
|---|---|---|
|`5d5750c`|既存のprivate Jobを持つ子を、別の所有Jobで管理。全JobのPID照会・停止・解放を行い、constructor途中の二重失敗でも呼出元に所有を残す|映像venvでの実Windows API失敗、カメラなしの専用fixture、解放・割当失敗の注入|
|`2be24e7`|dots/MandalaのQUIT・Esc・q、runnerのreturn/例外、Managerの停止要求を対応付けて記録|現行の実sceneを使ったイベント注入、実runnerと子出力回収、閉じたstdoutでの停止処理|
|`270b315`|`Check Mac Connection.cmd`によるカメラなしの疎通確認|loopbackの実HTTP、禁止アドレス・競合ポート・既存ログの保護、時間終了とポート解放|
|`91b3200`|自然復帰を切替成功の回数に数えない。全昇格と生存シーンの交代を分離|自然復帰20回だけで指定回数に達する赤い試験、待機中の旧終了、復帰後の正規交代、停止失敗、両Pythonの120件回帰|

すべて `codex/rebirth2026-production-candidate` へ通常push済み。main/stableへの統合やforce pushはしていない。

## Windows Jobの切り分け

同じソースでも、前段階のPython 3.11での94件成功を、映像用venvの成功へ読み替えられないことが分かった。

|実行|結果|
|---|---|
|映像venv Python 3.12.10で既存94件|93件成功、late Job取り込みの1件がWinError 5|
|同venvでWindows launcher 4件だけ|同じ1件が再度失敗|
|Python 3.12本体を直接使い、late Job 1件|成功|
|映像venvでlate Job 1件|同じ失敗|
|private Jobを持つ子の専用fixtureをPython 3.11で実行|0.120秒で同じ失敗を再現|

仮説は①既存Job階層との衝突、②取り込み中のプロセス終了、③権限不足の順に調べた。一時プローブで、保持した同じプロセスハンドルが生存中・既存Job所属と確認できた状態で、root Jobへの割当はerror 5、空のJobへの割当は成功した。追加の管理者権限や待ち時間を変更せず結果が変わったため、既存Job階層との整合を修正対象とした。

Windowsは既存Jobに属するプロセスを割り当てるとき、空のJobまたは既存の階層と整合するJobを要求する。階層を作れない順序の割当は失敗する。[AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)、[Nested Jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs)。この仕様と上記の実測を照合した判断であり、Pythonの版だけを原因と断定していない。

修正は、型・生存・所有Job所属・親子関係を確認した子だけに限定する。既存root Jobへの割当がerror 5で、その子が生存して別Jobに属する場合、制限を維持したまま新しい空のJobで保持する。新しいJobへの割当が失敗すれば起動失敗として残し、成功したふりをしない。無関係PIDを取り込むfallbackはない。

独立レビューで、constructor後半の採用失敗とclose失敗が重なると、未解放Jobが呼出元へ渡らない経路も指摘された。これを新規試験で再現したうえで、root割当成功直後に `process._scene_job` へ所有を登録。元の例外と解放失敗の注記を保持し、後から残存Jobだけを再解放できるようにした。独立再確認でもこの所見の解消を確認した。

## 前段階3コミットの自動検証

修正後のコマンドは両環境とも `python -X utf8 -m unittest discover -s tests -q`。映像側は既存venvの絶対パスを指定した。

|環境|結果|ログ|
|---|---|---|
|PATHのPython 3.11|**112件 / 11.220秒 / OK / exit0**|`test_reports/continuation_regression_base_20260906.stderr.log`|
|映像venv Python 3.12.10|**112件 / 13.421秒 / OK / exit0**|`test_reports/continuation_regression_graphics_20260906.stderr.log`|

新規18件はWindows Job 5件、退出観測8件、Mac疎通5件。回帰はカメラを開かず、実Windowsプロセス・Job・TCP・共有メモリと疑似描画/カメラを使用した。ソース51ファイルのSHA-256を `test_reports/continuation_sources_20260906.json` に記録し、コードコミット後も不一致0件を確認。単発の失敗を隠して合格にしていない。

再現証跡は `test_reports/graphics_python_regression_20260906.stderr.log`、`nested_job_red_20260906.stderr.log`、`job_assignment_trace_20260906.stdout.log`、`nested_job_owner_red_20260906.stderr.log`。一時プローブは `test_reports/` のみに置き、製品コードにDEBUG出力を残していない。

## 退出理由の読み方

- 子の `[SceneLifecycle] exit_request` は、受信したQUIT・Esc・q、Mandalaの既存の読み取り失敗終了を区別する。誰がその入力を発生させたかは断定しない。
- `runner_end` は通常return、SystemExit、Python例外、KeyboardInterruptを区別する。終了コードと例外は維持する。この時点ではatexit解放・OSプロセス終了の完了を保証しない。
- Managerの `scene_stop_request` と `scene_exit` はlaunch_id・launcher PID・実Python PIDで子の記録と相関する。Managerの切替/終了要求と、子が自分で終了した場合を分けて読む。
- メインループに来た「次へ」の詳細はconsoleのキーボード操作行等とも照合する。過去の観測だけから、古いdots/Mandalaの終了原因が確定したとは記録しない。

## C922n実機とMac接続

ユーザーのTD終了後、OS上でもTD・StreamDiffusionプロセスがなく、8766/8767が空いていることを確認して起動した。基準は `finger_colorfull_dots_acer.py` のみ。起動は `Start Kids Test.cmd --duration-minutes 30 --operator-host <AcerのWi-Fi IPv4>`。

実機試験は **11:04:03〜11:34:03、1800.656秒で正常終了**した。試験IDは `test_reports/kids_trial_20260906_110351_124696400/`、`duration_reached / exit0`。実行したソースは`270b315`で、終了後も開始時51ファイルのSHA-256と不一致0件だった。

11:05:40と11:18:45の切替は、終了後に回収できたManager consoleの `Keyboard next scene` 2行とも照合した。旧子はKeyboardInterruptで終了した。11:18:28と11:18:32の子からの終了は、追加ログで両方 `key_escape` → `return` → launcher exit0と判別できた。入力元の人や装置までは断定しない。**30分単一シーン無中断の合格とはせず、操作・復帰を含むManager/カメラの運転記録として評価する。**

|確認項目|今回の結果|
|---|---|
|制御|5起動すべてでREADY→START→START_ACK→FIRST_FRAME。うち2回はEsc終了後の復帰|
|共有カメラ|全180 sampleで同じ共有メモリ名。フレーム152→53,995、read_failures=0、reopen_attempts=0、last_errorなし|
|フレーム更新|取得スレッドの最大フレーム間隔0.172秒、sample時の最大age 0.047秒。実パネルの更新速度ではない|
|Manager資源|Private Bytesの5〜10分中央値700,104,704 bytes→25〜30分700,067,840 bytes。ハンドル800〜810、GDI24〜25、USER20〜22|
|子シーン資源|PID 8048と32460の各区間は約770〜788MB、ハンドル652〜666。別PIDの前後中央値を1つの30分無中断試験として比較しない|
|終了後|Managerと5組のlauncher/実Python、計11 PIDの残留0。旧共有メモリ、セッションファイル、8766/8767/8768のlistenerも残留なし|
|未観測|パネル上の映像/座標、GPUメモリ・温度、子供・複数人、Macからの通信|

根拠は同試験の `runtime.jsonl`、`scene_output.jsonl`、`observed_summary.json`、`post_run_source_and_shm.json` と `test_reports/candidate_30min_20260906_1103.stdout.log`。OSプロセス一覧は終了後の読み取りで確認した。人物画像や録画は保存していない。

この版の `run_end.completed_switches=4` は、初回を除く昇格4回を意味し、正常な旧→新の交代2回とEsc復帰2回を合算していた。切替回数の判定に同じ値を使うため、復帰だけで指定20回の完走を記録できる条件をカメラなしで再現した。以下の追加修正対象とし、旧ログの4を「正規の切替4回」と読み替えない。

## 切替回数の追加修正と最新の検証

`91b3200`では、初回・自然終了からの復帰を含む全昇格を `completed_promotions` に残し、`completed_switches` は旧シーンがFIRST_FRAME時と旧停止直前の両方で生存し、その停止が成功した交代だけにした。間隔タイマーは復帰を含む昇格後に再設定する。通常の無人復帰を止めず、試験の誤った完走だけを防ぐ。

修正前の回帰では、自然復帰だけで `switch_count_reached` になった。修正後は初回＋自然復帰20回で **昇格21／切替0**。FIRST_FRAME前・overlay待機中の旧終了も切替に含めず、復帰3回後に指定した正規交代1回を実行すると切替1で終了する。独立レビューで修正必須所見はなく、停止失敗時のカウント不変と旧handle保持も追試した。

|環境|全回帰|ログ|
|---|---|---|
|Python 3.11|**120件 / 11.050秒 / OK / exit0**|`test_reports/switch_count_regression_base_20260906.stderr.log`|
|映像venv Python 3.12.10|**120件 / 13.009秒 / OK / exit0**|`test_reports/switch_count_regression_graphics_20260906.stderr.log`|

追加8件の前後でソースを固定し、対象51ファイルのSHA-256を `test_reports/switch_count_sources_20260906.json` に記録した。コミット・push後も不一致0件。自動回帰は物理カメラ・実描画の検証ではない。

ログの `sample.switch_count` / `run_end.completed_switches` はこの版から正規交代数。全昇格は新しい `sample.promotion_count` / `run_end.completed_promotions` で読む。旧ログを新定義として再解釈しない。別タスクのstatus_dashboardと現Operator UIには、今回変更したカウンタ名を直接読む処理は見つからなかった。

## 修正後の実20回切替

既存Python・C922n・基準dotsのまま、`--switch-every 20 --switch-count 20 --duration-minutes 30` を指定した。試験IDは `test_reports/kids_trial_20260906_114623_279319100/`、ソース`91b3200`。**11:46:34〜11:53:41、426.203秒で指定の20回を完走**した。consoleは子から直接保存し、一時の操作UI認証値は共有資料に含めない。

|確認項目|今回の結果|
|---|---|
|終了記録|Managerのrun_endは `switch_count_reached / exit_code=0 / completed_switches=20 / completed_promotions=24`|
|復帰の除外|初回1＋正常交代20＋Esc復帰3。復帰3回を切替完了数へ加算していない。Nextキー操作も1回含む|
|起動同期|24回すべてREADY→START→START_ACK→正のframe_idのFIRST_FRAME。正規交代20回の旧停止要求は、それぞれ新FIRST_FRAMEより後のログ順序|
|カメラ|全43 sampleで同じ共有メモリ名。read_failures=0、reopen_attempts=0、last_errorなし。最大フレーム間隔0.235秒、sample時の最大age 0.047秒|
|所有資源|sampleの対象プロセス数3〜5。ManagerのPrivate Bytesは699,912,192〜700,301,312 bytes、handles804〜818、GDI24〜25、USER20〜22|
|終了後|起動補助を含む49個の記録PID値をOSと照合し、現存0。途中のPID再利用はcreation_ticksで分離した。旧共有メモリとセッションファイルも消滅|
|版の照合|試験終了後もソース51ファイルのSHA-256不一致0件|

根拠は `observed_summary.json`、`invariant_check.json`、`post_run_processes.json`、`post_run_source_and_shm.json`、元のruntime/scene_outputと `test_reports/candidate_switch20_20260906.stdout.log`。起動用PowerShell helperの `Process.ExitCode` は空だったため、外側のexec exit0を実PythonのOS終了コード0へ読み替えない。上表のexit0はManager自身の終了記録。helperの終了値取得はカメラなしの別プローブで修正・検証済み。Windows PowerShell 5.1と同じ映像venvで、旧処理は子の終了値0/7が両方null、待機前にProcess.Handleを取得した後は0/7を保持した。検証は `test_reports/verify_trial_exitcode_20260906.ps1` の4組で、製品コードは変更していない。この理由で実20回をもう一度実行したり、過去のnative終了値を後付けで確定したりしない。

11:49頃にユーザーから「obsが立ち上がっていたので終了した」と申告を受けた。11:49:49のOS読取でOBSプロセス不在を確認。9回切替時点のカメラは同じ共有メモリ名、取得失敗・再取得0件だった。`observer_notes.jsonl`へ外部条件の変化として残し、OBSがカメラを使用していたか、終了が性能に影響したかは断定しない。試験を無操作・外部負荷一定の測定とは扱わない。

## Mac側で進行中の接続準備

Macの接続方式は未回答なので、最初の疎通だけ現在のWi-Fiで試せるようにした。専用ページはAcerからHTTP 200を確認し、Macでの到達は未確認。ページの一時URLはGitに保存しない。カメラを使わない入口・10分の自動終了・ログの読み方は [OPERATOR_PANEL.md](OPERATOR_PANEL.md) を参照。本番UIの認証・露出/ズーム適用を疎通だけで合格にしない。

2つの疎通プローブは10分の期限で終了。応答を確認した方の接続記録はAcer自身からの1件だけで、Mac到達の証拠はない。RTKの子出力が終了時までバッファされる経路を避けるため、後者は `Start-Process -WindowStyle Hidden` から子のstdout/stderrを直接ローカルログへ送った。既存listenerやfirewall設定は変更していない。

ユーザーから「別タスクでMacの接続手順を進めており、申告せず接続するかもしれない。今の作業は止めない」という追加前提を受領した。既存Wi-Fi側の明示IPv4で、カメラなしの疎通入口を30分の待受として再起動した。疎通ページのアクセス記録とAcerの接続アドレスを並行確認する。別タスクでの準備をMac通信成功と読み替えず、接続方式を勝手に最終決定しない。

11:38:56開始の30分待受はアクセス0件で期限終了し、PID/listenerの消滅を確認した。Mac準備が続く前提で、**12:10:47〜13:10:47頃の1時間待受**を新たに用意した。カメラや描画を起動せず、接続の申告がなくてもアクセス時刻・送信元IPをローカルに記録する。現在の一時URLは `test_reports/mac_link_standby_20260906_1210.stdout.log`、接続記録は同名の `.jsonl`。終了後は `Check Mac Connection.cmd` から新しい待受を作る。最終照合時点でこの入口へのMac到達は未確認。

新しい1時間待受はAcer自身からHTTP 200を確認した。この自己アクセスはログに残るが、Mac側の到達証拠にはしない。

## 次候補の依存確認と環境判断

サブエージェントが `finger_grid_interaction_acer.py`、`particle_storm_acer.py`、`saturn_particles_acer.py` と各 `_2.py` を読み、指定映像venvのmetadata・nativeファイル・モデルの存在/サイズを確認した。`-I -S -B` でsitecustomizeとキャッシュ書込みを避け、描画系import・モデル読込・GPU要求・カメラ/ウィンドウ起動を行わない検査である。

推移依存を含む40配布の不足・有効な版条件違反は0。pygame 2.6.1、MediaPipe 0.10.14、NumPy 2.2.6、pygfx 0.16.0、wgpu 0.31.0、rendercanvas 2.6.3、pylinalg 0.6.8、glfw 2.10.0、screeninfo 0.8.1が存在した。grid用の内蔵full handモデルは5,478,917 bytes、full palmは2,339,846 bytes、tracking graphは2,901 bytes。3Dの2本が使う `models/hand_landmarker.task` は7,819,105 bytesで第一候補が解決した。3本に外部画像/音声asset参照はなかった。これだけでABI整合・モデル実読込・GPU描画や本番採用は合格にしない。

OpenCVのmetadataはcontrib 4.12.0.88と通常版4.13.0.92が併存し、実ファイル `cv2/version.py` は4.12.0.88・contrib=Trueだった。再現可能な別環境を作る際の整理対象として残す。現在の実試験が使う環境を途中で変更せず、これを今回の映像障害の原因とは断定していない。

## 保留とロールバック

今回の同一シーン20回は、実C922nを使った制御・回復・所有資源の観測として完了。無操作・一定負荷・異種GPUシーン間の合格ではない。子供・複数人と5点座標、Mac実通信、Xiaomi、30分無中断、異種シーン、実USB復帰、12時間はHuman Check Required。共通透過率の対象も回答待ち。12時間試験は開始していない。今回のJobエラーは既存権限内で修正でき、未解決のPermission Blockedにはしていない。

次は大人がAcerで映像と指先の5点を確認し、Macの疎通→認証済みUI→実設定の反映を照合する。その後、操作の入らない時間を確保して単一シーン30分、実USB復帰、候補grid→particleの順で確認する。既に操作が混じった試験を無中断合格にせず、ユーザーがMac接続準備中のAcerへ30分試験を繰り返し立ち上げない。実地入口は [KIDS_TEST_START.md](KIDS_TEST_START.md)、画面を終了するにはManager Controlのqまたは操作UIの「Managerを終了」を使う。

この順序は現在のCodex側の運用判断であり、ユーザーが30分試験を禁止したという記録ではない。目視・接続・無操作の試験時間を確保できた条件に合わせて次の確認を進める。

復元時はManagerを通常終了し、所有PIDとカメラ解放を確認する。今回の回数判定だけの比較基点は`270b315`、先行3件も含む比較基点は `d2864f1`。必要な場合に候補コミットを `91b3200` → `270b315` → `2be24e7` → `5d5750c` の順でrevertし、main/stableや別タスクの未保存成果物を巻き戻さない。旧回数判定やJob問題も戻るので、比較版を実機合格済みとは扱わない。

## 最終の資料照合

Markdown 10本のローカルリンク74件に欠落なし。候補レポートの61ファイルは基点`260ee87`からのGit差分と一致し、実行ソース51ファイルも最新120件回帰時のSHA-256と一致した。`git diff --check`成功。iPhone資料2本にも版・実測・未確認を反映した。別タスクの動的HTML、`status_dashboard/`、`TD_BUSINESS_RESEARCH_20260906.md`は今回のコミット対象に含めない。
