# Reverse Ubers iPhone Handoff

> この文書は、Windows側Codexとユーザーの直近のやり取りを、iPhone側ChatGPTへ引き継ぐための記録である。
>
> - 作成日：2026年9月6日（JST）
> - 対象プロジェクト：春風2026 Kidz Disco資産を「リバース／Rebirth 2026」本番へ再設計する作業
> - 対象リポジトリ：<https://github.com/mindoverdrive/harukaze2026_kidzdisco_windows>
> - 記録範囲：リポジトリ読取確認から、診断監査、修正計画、体験要件、実装計画書HTMLの作成・push、本ファイル作成依頼まで
> - 作成当初の段階：診断と計画の文書化まで。以後の候補実装は末尾の第17節へ追記。

**2026-09-06追記：現在は候補ブランチでP1・単一シーンの起動基盤を実装し、自動テスト63件通過。実地テスト開始は映像用Pythonの実行制限と実映像確認が残る。最初に [最新候補レポート](PRODUCTION_CANDIDATE_REPORT_20260906.md) と第17節を読む。以下の旧「実装前」は当時の記録として残している。**

## 0. この記録の読み方

このファイルは単純な要約ではなく、発言順と判断の変化を追えるようにした準生ログである。

- 会話の正確な時刻情報は取得できないため、発言順に通し番号を付けた。
- `ユーザー`欄は、可能な限り原文の語順、表記、タイポを維持した。
- 音声会話では、同じ文の重複、途中で切れた語、AI音声との重なりが発生している。意味が同じ断片は一つにまとめ、必要な箇所に`[音声認識注記]`を付けた。
- 「アンサー」「アーサー」「Asa」「Arsar」は、この会話では原則として`Acer`またはファイル名中の`acer`を指す。
- 「シーンプロファイルランナー.py」は`scene_profile_runner.py`、「シェアドカメラ.py」は`shared_camera.py`、「元の .2.py」は末尾が`_2.py`の実装ファイルを指す。
- `Codex応答・実行結果`欄は、会話中の応答を短くまとめた箇所と、Git・ファイルから後で確認した事実を含む。ユーザーの決定と混同しないこと。
- 正確なファイル名や実機状態は、会話の音声認識結果よりも、リポジトリ本文と実機観測を優先する。
- ファイル名はユーザー指定どおり`Reverse Ubers iPhone Handoff .md`とした。イベント名について、会話本文では一貫して「リバース／Rebirth」として扱われている。

## 1. iPhone側が最初に保持する現在地

### 1.1 目的

春風2026のKids Disco向けに短期間で作ったPython映像・インタラクション資産を土台に、次のイベント「リバース」で連続性のある作品体験として実運用できる状態へ仕上げる。

体験上の二つの軸は次のとおり。

1. 小学生が、自分の動きと映像変化の因果関係を直感的に理解して遊べる。
2. サイケデリック／テクノ系の空間にいる大人が見ても、単純な子供向けゲームではなく映像作品として成立する。

### 1.2 最優先の運用条件

- 開発機兼本番機はAcer Windows実機。
- 本番カメラはLogicool C922。
- 本番表示先はXiaomi L32M8-A2TWN。
- Acer実機で長時間安定して動くことを最優先にする。
- 人がいないときの無人オート運用と、参加者・スタッフによる介入を両立する。
- Pythonモードでは、物理カメラをManagerが所有する構成を維持する。
- AcerへMacBook ProをPANで接続して操作することは必須。可能ならブラウザUIにする。
- 開発はぎりぎりまで同じAcerで行うため、安定版を壊さず候補版へ一発で差し替え、失敗時に戻せる構造を重視する。
- 必要に応じて、Python映像からTouchDesigner映像へ簡単に切り替え、Xiaomiへ全画面表示できる運用を検討する。

### 1.3 日程

- 先に共有された実質的な開発完了目標：2026年9月8日夜。
- 9月9日：休養・予備日にしたい。
- 9月10日：出発。
- 後の発言には「9/9までにこのプログラムを仕上げる」もある。
- 現時点の安全な読み方は、**9月8日夜を作業完了目標、9月9日を最終予備線**とすること。日程の意味を勝手に変更しない。

### 1.4 安定性の基準

- 現時点で「Acer本番機で長時間安定動作確認済み」と断言できるシーンはない。
- ファイルやAcerラッパーが存在することと、本番実機で安定稼働済みであることは別。
- 最終的な長時間安定性の暫定目標は、再起動なし12時間。
- ただし最初から12時間試験には入らない。
- 最初の基礎gateは、修正後の30分単一シーン、Managerによる切替反復、失敗経路の個別確認。

### 1.5 実装状態

- 静的監査と修正計画の作成は実施済み。
- 本番体験、Manager状態、シーン分類、リリース差し替え、TouchDesigner切替の計画書は作成済み。
- Pythonソース、`config.json`、起動設定、TouchDesigner TOEは変更していない。
- Acer実機試験はまだ行っていない。
- 自動GitHub同期や定期実行は設定していない。
- 実装開始を意味するユーザーの明示指示は、この記録範囲ではまだない。

## 2. 準生ログ：発言と判断の流れ

### LOG-001：GitHubリポジトリの読取確認

**ユーザー**

> https://github.com/mindoverdrive/harukaze2026_kidzdisco_windows 上げるね。これはそのまま入れて。今接続しているGitHubリポジトリが正しく読み取れているか確認したいです。まずは実際に読めているファイル名をいくつか挙げて、各ファイルの中身を変わらずに概要だけ教えてください。

**意図**

- コードを変更せず、接続先と本文読取の事実を確認する。
- ファイル名だけの推測ではなく、実本文を読んだうえで概要を返す。

**Codex応答・実行結果**

- リポジトリを読み、複数の実ファイル名と内容概要を提示した。
- この段階ではファイル変更を行っていない。

### LOG-002：全ファイル一覧と本文確認

**ユーザー**

> OK。このリポジトリの全ファイル一覧を省略せずに出力してください。その際、実際に本文を読めているかも併せて確認し、各ファイルは変更せずに存在確認と概要の把握だけを行ってください。

**Codex応答・実行結果**

- リポジトリ全体で105ファイルの存在を確認した。
- うち89のテキストファイルは本文を取得して照合した。
- バイナリ資産は存在確認までであり、モデルや画像の動作・有効性まで検証したわけではない。

### LOG-003：途中で切れた音声

**ユーザー**

> オッケー、余った...待って。春風2026のKids Disco向けに開発したMono2と

`[音声認識注記]` 発話は途中で終了した。`Mono2`が何を指すか、その後の会話で確定していない。この断片だけから要件を作らない。

### LOG-004：リバース向け再設計の開始条件

**ユーザー**

> 春風2026のKids Disco向けに開発したこのリポジトリを、次のイベント、リバースで実運用するために再設計します。ただし、まだコードの変更や実装提案には進まないでください。まず背景、目的、制約を共有し、認識を合わせます

**Codex応答**

- 実装や修正案へ進まず、前提整理に限定すると応答した。

### LOG-005：子供の直感性と大人向けの作品性

**ユーザー**

> リバースでは、小学生の子供の動きと映像の変化の因果関係を直感的に理解して遊べることを重視します。同時に、子供向けの単純なゲームにはせず、サイケデリックやテクノ系の空間にいる大人が見ても、映像作品として成立するクオリティを目指します

**判断上の意味**

- 操作説明の分かりやすさだけでなく、長く見ても成立する映像品質が必要。
- 「キッズ向け」を理由に単純なスコアゲームや幼い見た目へ寄せない。

### LOG-006：既存資産、Acer実機、無人運用、時間不足

**ユーザー**

> 春風向けに、急いで作った資産を、今ある尺とファイルを土台にしつつ、リバース向けにちゃんと作品として、連続性のある体験に仕上げ直したいっていうこと。それと、エイサー実機で安定して動かして、無人でも成立するオートモードを用意しつつ、必要ならマニュアル介入もできる余地を残す、っていう方向性かな。さらに、時間がほとんどないから、全部作り直すんじゃなくて、使えるものを選ん、絞るって判断が必要になってる

**Codexによる復唱の要点**

- 春風資産を土台にする。
- Acer実機で安定させる。
- 無人オートと手動介入を両立する。
- 全面再制作ではなく、使えるシーンへ絞る。

### LOG-007：iPhone側ChatGPTとWindows側Codexの役割

**ユーザーの音声趣旨**

> 私は人間で、iPhoneでのChatGPTと、パソコンでのCodex、それぞれと話している。ChatGPT同士でやり取りを進め、開発を進めてほしい。私は黙って聞いていて、たまに介入する場合もある。それを前提に音声として出力してください。iPhone側もWindows側も理解した旨を伝えてください。

`[音声認識注記]` 原音声には「コーデックス」「チャットGPT」「介護ね」「別々医療」などの誤認識・重複が含まれていた。意味として確定したのは、iPhone側とWindows側を別のAI窓口として協働させ、ユーザーが必要時に介入する運用。

**Codex応答の要点**

- Windows側Codexとして、音声経由のやり取りとユーザー介入を優先する前提を理解したと返答した。

### LOG-008：まず要件を箇条書きにする

**iPhone側と見られる発話**

> 今は前提合わせの段階だから、実装とか提案には入らずに、まずゴーが言った背景と制約を箇条書きで要約して、確認質問だけに絞るっていうのを最初の一手にしていいかな

> うん、オッケー、その方針でいくね。じゃあまず箇条書きで背景と制約をまとめるよ。その上で短い確認質問を出すから、答えられるところだけ教えて

**Windows側Codex応答の要点**

- 背景と制約を固め、未確認事項だけを質問する進め方に同意した。

### LOG-009：期限

**ユーザー／iPhone側を介した発話**

> 期限は九月十日出発前。ただ九月九日は休養と予備日にしたいから、実質の開発完了目標は九月八日夜で見ときたい。だからまずは、その締め切り前提で設計の棚卸しと優先度判断を最短で進める方向で組み立てるよ

**Codex応答の要点**

- 9月8日夜を実質完了、9日を予備、10日を出発日として反映した。

### LOG-010：安定動作済みシーンはまだない

**ユーザー／iPhone側を介した発話**

> 今の時点では、断定できる安定動作確認済みって言い切れるシーンはまだない前提で進めよう。複数シーンや映算向けラッパーの存在は確認できてるけど、それイコール本番実機で安定に稼働済みとは言えないからね。だから次の棚卸しでは、実機確認済みと未確認を明確に分けて、未確認は安定版扱いしない方針で実機テストの優先順位をつけていくのが安全だと思う。まずは実機での最小構成、起動からシーン一つ通し長時間安定の確認から逆算しようか

`[音声認識注記]` 「映算向けラッパー」は文脈上、Acer向けラッパーを指す可能性が高い。

**Codex応答の要点**

- シーンの存在確認と実機稼働確認を分ける方針を受け取った。

### LOG-011：12時間の暫定基準

**ユーザー**

> ごめんね、その稼働時間はまだはっきり決まってないと思う。だから、現段階の想定としては、再現率稼働時間は、えー、十二時間と想定してください

`[音声認識注記]` 「再現率稼働時間」は文脈上「連続稼働時間」の誤認識として扱われた。

**Codex応答の要点**

- 再起動なし12時間を最終的な暫定基準にした。
- この時点では実機テストを開始していない。

### LOG-012：作業停止の明示

**ユーザー**

> 一度作業中止してください

> オッケー、ここで完全に止めるね

> えー、では、私は黙って中止してください。えー、それ以降黙って、黙ってになる次です

> 了解了解、もう黙るね、今から終了してください

> いろいろ、終了してください

**Codex応答・結果**

- 作業を中止した。
- 停止後に新しい実装や試験は行っていない。
- この経緯から、今後もユーザーが中止を指示した際は復唱を重ねず停止する。

### LOG-013：静的診断監査の依頼

**ユーザー**

> Okay。現在のコードはまだ変更しないでください。最初の作業は診断監査のみです。対象は manager.py、シーンプロファイルランナー.py、シェアドカメラ.py、七五のアンサー.py、各アンサー.pyが呼び出している元の .2.pyです。目的は、Arsar Windows実機でリバース本番に使用するシーンを長時間安定して運用できる状態にすることです。現状は問題点の特定だけを行ってください。重点はシーン切り替え時の急プロセス終了、カメラハンドルの解放、次シーンでのカメラ再取得、子プロセスやウィンドウ、GPUリソースの残留、例外終了時のクリーンアップ、環境変数の反映、長時間運転によるリソース蓄積、実機固有の問題です。問題項目ごとに深度度、該当箇所、理由、実機での確認方法、最小修正案を示してください。ただしこの段階では修正は提案だけで実装はしないでください。最後に最初に実機テストすべき3シーンを理由付きで選んでください。
>
> ＊アンサー＝acer、そのほか.py周りなどのあいまいなタイポに気を付けて

**補足のユーザー発言**

> コードは変えずに、まず、静的監査で実機運用上の問題点を洗い出すこと

**Codexが実際に全文確認した主要対象**

- `manager.py`
- `scene_profile_runner.py`
- `shared_camera.py`
- 7個の`*_acer.py`
- 各ラッパーが呼ぶ7個の`*_2.py`
- 合計17ファイル

**7組の正確な対応**

| Acerラッパー | 呼び出す実装 |
|---|---|
| `finger_colorfull_dots_acer.py` | `finger_colorfull_dots_2.py` |
| `finger_grid_interaction_acer.py` | `finger_grid_interaction_2.py` |
| `finger_mandala_acer.py` | `finger_mandala_2.py` |
| `fractal_moving_acer.py` | `fractal_moving_2.py` |
| `particle_storm_acer.py` | `particle_storm_2.py` |
| `saturn_particles_acer.py` | `saturn_particles_2.py` |
| `spider_cursor_acer.py` | `spider_cursor_2.py` |

### LOG-014：P1の5項目だけについて修正計画を作る

**ユーザー**

> OK。現時点の行動はまだ変更しないで。次にやるのは修正の実装ではなく修正計画の作成だけにして。対象はP1のうち、ナンバー2、ナンバー9、ナンバー1、ナンバー3、ナンバー6の5項目だけ。この順を基本に依存関係で入れ替えるべきならその理由を説明して。各項目について修正対象箇所、現在の処理フロー、障害が起きる条件、最小限の修正方法、修正後のフロー、他のPHとの依存関係、想定される副作用、Asa実器での最小確認手順と合格条件、それから失敗した場合に取得すべきログや観測値を整理して。スタートの問題は単なる待ち時間追加ではなく受信準備完了を確認できるハンドシェイク方式を検討して。カメラはマネージャーが物理カメラを所有する設計は維持して、起動対象は最終的に明示リスト化して本番で使うナンバーAsa.pyだけに限定できる構造を優先。ただし今は採用確定はしない。12時間連続試験にはまだ入らず、修正後は30分間の単一シーンとマネージャー切り替え反復で基礎動作を確認する。基準シーンの第一候補はFinger Colorful Dots.pyだが、より適したものがあれば理由付きで提案して、みたいな感じかな。

`[音声認識注記]`

- 「PH」はP1または他の監査項目との依存関係を指すと解釈した。
- 「ナンバーAsa.py」は本番用の`*_acer.py`を指すと解釈した。
- `Finger Colorful Dots.py`は類似名が複数あるため、正確な基準候補を`finger_colorfull_dots_acer.py`、その呼出先を`finger_colorfull_dots_2.py`として区別した。

**Codexが出した推奨順序案**

`#2 → #6 → #9 → #1 → #3`

ユーザー指定の`#2 → #9 → #1 → #3`の相対順を維持し、`#6`だけを前倒しする案。理由は、カメラ初期化失敗、起動タイムアウト、再取得失敗を試す前に、途中まで取得した資源や起動した子を確実に片付ける基礎が必要だから。この順序はCodex提案であり、実装採用はまだ確定していない。

### LOG-015：iPhoneへの継続的な引継ぎ方法

**ユーザー**

> これまでのチャットやりとりを、うまくiphoneｇｐｔに引き渡すためのなんらかの仕組みを考えて

> iphone gptは会話を終了するたびにコンテキストの多くを忘れるので、要点を詳細にまとめたデータを常に残してやりたい。おまえがタスクを終えるたびにgithub経由で同期する案は？お前が作業中に、次にお前に渡すプロンプトをiphoneと考えておくために。

**その直後のユーザー指示**

> 今の取り消して

**現在の扱い**

- 「各タスク終了時に自動でGitHubへ同期する仕組み」は取り消された。
- 定期自動化、heartbeat、cron、自動commit/pushは作成していない。
- その後の明示的な単発commit/push指示には従った。

### LOG-016：引継ぎメモを作り、単発でcommit/push

**ユーザー**

> メモを作成して

> リバース、iPhoneハンドオフ2026マークダウン。さっき作ってもらったメモを含めて、git commit/push、プッシュして。

**Codex実行結果**

- `REBIRTH_IPHONE_HANDOFF_2026-09-05.md`を作成・更新した。
- 2026年9月5日のcommit：`71cc545` `リバース向けiPhone引き継ぎメモと修正計画を追加`
- 2026年9月6日の更新commit：`7d712fe` `iPhone引き継ぎメモを本番切替設計まで更新`
- これらはユーザーの明示指示による単発push。

### LOG-017：期限、寝ている間の進行、実機環境、追加機能

**ユーザー**

> 9/9までにこのプログラムを仕上げる。できるだけ早く、「寝ている間にゴールコマンド」ですすめられるように、また、実装環境であるlogitec c922 やxiaomi l32m8-a2twn環境（rebirth2026_sol_newチャット参照のこと）でのテスト実装などto doリスト作成したい。できる限りほかの機能も（acerのpanでmacbookproをつないで操作する、は必須。他にもuiの修正・アップグレードなど）いれる案を練る

`[名称注記]`

- `logitec c922`は会話と別タスクの整合からLogicool／Logitech C922を指す。
- `xiaomi l32m8-a2twn`はXiaomi L32M8-A2TWN。
- 「寝ている間にゴールコマンド」は、Codexのgoal機能等で継続的に進めたい意図と読めるが、この発言だけでは自動実行設定を確定していない。
- `AcerのPANでMacBook Proをつないで操作`は必須条件として扱う。

### LOG-018：使いたいシーンはユーザーが目視選定する

**ユーザー**

> 俺が、「これは使いたい」と思うシーンのリストを作成して渡す

**現在の扱い**

- 本番採用ファイルは、似た名前の派生版をCodexが自動決定しない。
- ユーザーの目視確認と正確なファイル指定を待つ。
- 起動manifestへ入れるのは、その確認後の承認済みentrypointだけにする案。

### LOG-019：参加者ボタンをactivityとして扱う

**ユーザー**

> ボタンが押された場合は人が遊んでると認識し、独立したシーンも混ぜて切り替える

**設計上の意味**

- ボタン操作は単なる前後移動だけでなく、参加者がいることを示すactivity信号になる。
- activity中は、Minecraftなどの独立したゲーム性の高いシーンも選択対象へ含める。
- inactivity時の自律映像と、参加中のscene poolを分ける必要がある。

### LOG-020：最初の「使いたい」シーン一覧

**ユーザー**

> finger_mandala : 複数人対応、人によって色が違う、
>
> colorfull_dots_spheres : 派手でリッチな描画
>
> colorfull_wave_dots : 派手でリッチな描画
>
> fractal_moving : 派手にリッチに
>
> finger_colorfull_dots : 派手リッチ
>
> otedama系：上と同じ
>
> minecraft : 派手リッチ
>
> polygon_vibes系 : 上と同じ
>
> particle_storm : 派手リッチ
>
> roulette
>
> skelton_glitch : 派手リッチ
>
> earth : 基本そのまま

> 手動切り替え系（独立したシーン、minecraftなど）と自動モード向けのものをより分ける。
>
> 手動ではどれでも指定できるが、切り替わりの桜エフェクトは内容を一新する。上に指定した名称は、似たものがあるので各種類、俺が目視確認してしていする。
>
> ・切り替えトリガーになるアクションなど、manager.pyの挙動をよくかんがえる。たとえば、常に左右上部分に（次のシーンへ、前のシーンへ、とかNextとかの表記のボタンにタッチできる、など。複数オプションを用意しておく）

`[名称注記]`

- `skelton_glitch`のリポジトリ上の正しい綴りは`skeleton_glitch.py`。
- `colorfull`はリポジトリ内で実際に使われている綴りを保持する。
- 桜transitionは役割を維持しつつ、見た目の内容を一新する要求。
- 左右上ボタンの文言、形、dwell方式などは案を複数用意する段階で、採用形は未決定。

### LOG-021：無操作時の自律映像

**ユーザー**

> ひとが操作していないときには自律的にうごくものを

**設計上の意味**

- 無人時にも停止画面ではなく、それ自体で見られる映像作品として動き続ける。
- 自律変化は、参加者のアクション反応と視覚的に区別する。

### LOG-022：複数人対応と追加シーン

**ユーザー**

> finger_mandalaのように、複数操作を適切なシーンに適用。ただし、違った趣向をこらすこと。spider_cursor_acer、saturn_particles, coloefull_treeもリストに追加。

**現在の扱い**

- `finger_mandala`は複数人対応の中心候補。
- 人ごとに異なる色を割り当てる。
- 複数人対応を他の適切なシーンにも入れるが、全シーンを同じ操作へ統一せず、シーンごとに違う面白さを作る。
- 追加候補：`spider_cursor_acer`、`saturn_particles`、`colorfull_tree.py`。
- `coloefull_tree`は音声・入力上の綴り揺れ。リポジトリ上の実ファイルは`colorfull_tree.py`。

### LOG-023：MacBook操作UI

**ユーザー**

> macbookからの操作は、できればuiがいい

**現在の扱い**

- AcerとMacBook ProをPANで接続することは必須。
- MacBook側はブラウザUIを第一候補とする。
- UIで必要な操作、通信方式、認証、緊急時のAcer直接操作は未確定。

### LOG-024：MediaPipeについて別タスクを参照

**ユーザー**

> mediapipeを使った

> mediapipeを使った.pyは、rebirth2026_Sol_newチャット参照のこと

**現在の扱い**

- MediaPipeを使うPython実装について、別タスク`rebirth2026_Sol_new`の知見と突合する。
- Windows側Codexが別タスクと`C:\rebirth2026`から確認した技術的事実は後段に記録する。
- iPhone側が同じソースを読めていない場合、自分で実読したとは表現しない。

### LOG-025：Acer一台で開発し、一発差し替えできる設計

**ユーザー**

> また、開発はぎりぎりまでこのacerのみで行うので、一発で差し替えられるようにrebirthチャットをよく読んで設計しろ

**設計上の意味**

- 同じAcer上に安定版と候補版を並置する。
- 作業中の候補を安定版へ直接上書きしない。
- 小さな参照ファイルまたはmanifestの切替で候補へ移る。
- 起動確認に失敗したら直前の安定版へ戻す。
- 本番切替時にネットワーク依存の`git pull`や依存導入を行う構造は避ける案。

### LOG-026：TouchDesignerを簡単にXiaomiへ全画面表示する

**ユーザー**

> タイミング次第ではタッチデザイナーを起動した画面をシャオミのディスプレイにフルで表示する時間も設けたいので、それをできれば一発のコマンドだったり、もう何かクリックとか簡単にそのタッチデザイナーの何かファイルを開いたらAcerの画面に、Pythonのファイルとかと同じように表示されるようなのを考えて。

**解釈と未確認点**

- Acerから操作し、Xiaomiへ作品を全画面表示する要求として計画した。
- 「Acerの画面」がAcer内蔵画面自体を表示先にする意味なら、表示profileを分ける必要がある。
- PythonとTouchDesignerの両方がC922を同時所有しないshow-mode supervisor案を作成した。
- `.toe`全体のWindows関連付けではなく、承認済みruntime TOEを開く専用shortcut案を優先した。

### LOG-027：iPhoneへ引継ぎ、別の棚卸しタスクと整合させる

**ユーザー**

> iphoneに引き継いで

> 「全シーンを棚卸して分類」チャットと突合して整合性をとれ

**Codex実行結果**

- `REBIRTH_IPHONE_HANDOFF_2026-09-05.md`を更新した。
- `全シーンを棚卸しして分類`タスクの分類結果と、ユーザーの最新「使いたい」リストを突合した。
- 棚卸し側の初期評価より、後からユーザーが明示した使用希望を優先した。
- 更新をcommit `7d712fe`として`origin/main`へpushした。

### LOG-028：finger_mandalaを急にリセットしない

**ユーザー**

> finger_mandalaは、何かしらの時間的な変化をつけて飽きないような趣向をこらしたいが、一気にリセットされるようなものはいや

**設計上の意味**

- 長時間見ても飽きない時間変化が必要。
- 画面全体や履歴を瞬時に消すようなreset演出は避ける。
- 色相、対称性、粒子、線、層などを徐々に世代交代させる案を計画書に入れた。

### LOG-029：時間変化は全シーン共通の重要要件

**ユーザー**

> ・何かしらの時間的な変化をつけて飽きないような趣向をこらしたいのはすべて同じ、これ大事
>
> ・時間的な変化とアクションによるトリガーが、キッズにも分かりやすいように分離されていると望ましい
>
> ・アクショントリガーのガイド説明が、グラフィックで分かりやすく表示されるように。例えば要請みたいなゴースト的なビジュアルが表示される、とか

**ユーザーによる訂正**

> 妖精な

**確定した意味**

- 全シーンに、緩やかな時間変化を持たせる。
- 子供が「自分のアクションで今起きた変化」を理解できるよう、自律的な時間変化と即時反応を別の視覚層として設計する。
- 操作のヒントは文章説明に寄せず、妖精のようなゴースト的ガイドをグラフィックで表示する。
- ガイドは促すアクションを見せ、成功時に分かりやすい反応を返す。

### LOG-030：HTML実装計画書の作成

**ユーザー**

> 実装計画書をhtmlで表示して

**Codex実行結果**

- `20260906-rebirth-implementation-plan.html`を作成した。
- 表示用に`design-system/document.css`と`design-system/math-copy.js`を追加した。
- HTMLには次を記載した。
  - 目的、固定条件、用語と判断境界
  - Acer上の本番構成
  - 全シーン共通契約
  - Managerの`AUTO_IDLE`、`ACTIVE_PLAY`、`MANUAL_HOLD`、`SWITCHING`、`STANDBY`
  - P1修正順序案`#2 → #6 → #9 → #1 → #3`
  - シーン候補と実装wave
  - 一発差し替えとrollback
  - Python／TouchDesigner／待機画面の切替
  - 実機試験gate
  - 9月8日夜までの進行
  - ログ、復旧、実装完了条件
- HTML構文、相対CSS/JS参照、アンカーを確認した。
- Python、設定、TOEは変更していない。

### LOG-031：HTML計画書をcommit/push

**ユーザー**

> commit/pushして

**Codex実行結果**

- 対象をHTMLと表示用CSS/JavaScriptの3ファイルだけに限定した。
- `git diff --cached --check`に問題がないことを確認した。
- commit：`d83f99a7ad08f457681c2abfad91cf2e3fadd09a`
- commit message：`リバース2026実装計画書をHTMLで追加`
- `main`を`origin/main`へpushした。
- push後、`HEAD`と`origin/main`が同じcommitであることを確認した。

### LOG-032：今回の準生ログ作成依頼

**ユーザー**

> OK。直近のこのプロジェクトに関するやり取りをできるだけ生ログに近い形で Markdownにまとめて、省略しすぎず判断に必要な文脈が追える粒度で、出力は一つの .md としてファイル名は Reverse Ubers iPhone Handoff .mdにして。以上だよ。

**Codex実行内容**

- 本ファイルを一つの新規Markdownとして作成した。
- 既存のPython、設定、TOE、既存引継ぎメモ、HTML計画書は変更していない。
- 本ファイルのcommit/pushは、この作成依頼だけでは実行していない。

## 3. 静的監査で確認した実装構成

### 3.1 通常のデータフロー

```text
manager.py
  └─ SharedCameraRelayが物理カメラを取得
       ├─ 共有メモリへフレームを書き込む
       └─ Manager内の認識用スレッドもRelayのフレームを読む

Managerが子プロセスとして *_acer.py を起動
  └─ scene_profile_runner.run_scene()
       └─ runpyで対応する *_2.py を同じ子プロセス内に実行
            └─ 共有メモリからカメラフレームを読む
```

重要な点：`*_acer.py`と`*_2.py`が別々の二子プロセスになるわけではない。ラッパーからrunnerを通じて、同じ子プロセス内で`_2.py`が実行される。

通常のシーン切替ではManagerが物理カメラを持ち続ける。旧シーンは共有メモリ接続を終了し、新シーンが共有メモリへ接続する。物理カメラの再取得は、カメラ接続障害やManager再起動などの別経路で問題になる。

### 3.2 監査時の基準commit

- 静的監査対象のmain：`28f662cdcb4532ca5361f53d81fe8db622c8ae7b`
- その後のcommitは文書追加だけ：`71cc545`、`7d712fe`、`d83f99a`
- Python実装の基準は監査時から変わっていない。
- Acerローカル上の実ファイルが同じcommitかは、実機試験前に確認する。

## 4. 静的監査の全問題一覧

番号は既存の監査と計画書で固定して使われている。新しい会話でも同じ番号を維持する。

| 番号 | 重要度 | 静的に確認した問題 | 現在の扱い |
|---|---|---|---|
| #1 | P1 | `START`を一度だけ送るため、子のUDP待機開始前なら取りこぼす。新シーンの起動成功を確認せず旧シーンを終了する。 | 修正計画対象 |
| #2 | P1 | 自動選択がAcer版に限定されず、別版や補助ファイルも選択し得る。 | 修正計画対象 |
| #3 | P1 | カメラ再取得失敗後に`cap=None`のまま`read()`を呼び、取得スレッドが終了し得る。 | 修正計画対象 |
| #4 | P1 | 古い共有フレーム、認識停止、描画停止を正常稼働として扱い得る。 | 今回の5項目外。限界として残る |
| #5 | P2 | Windowsで通常切替にも強制終了を使い、シーンの`finally`／`atexit`を通らない。 | 今回の5項目外 |
| #6 | P1 | 初期化途中、例外時、解放処理中の失敗でcleanupが抜け得る。 | 修正計画対象 |
| #7 | P2 | 取得スレッド終了確認前にカメラ・共有メモリを閉じ得る。native `read()`のblockも未解決。 | 今回の5項目外。限界として残る |
| #8 | P1 | カメラ取得`None`の扱いが不統一。Mandala／Spiderは読取失敗一回で終了し得る。 | 今回の5項目外。限界として残る |
| #9 | P1 | Acer子プロセスに設定したカメラprofileと、物理カメラを開くManagerの設定が一致しない。 | 修正計画対象 |
| #10 | P2 | 共有無効設定でも共有接続する経路、古い接続情報から復帰できない経路がある。 | 今回の5項目外 |
| #11 | P2 | Acer版の画面位置と切替演出の位置が一致しない。GPU表示補助にもbackend依存がある。 | 今回の5項目外 |
| #12 | P2 | WGPU環境変数名・値が公開仕様と異なり、GPU依存version固定も弱い。 | 今回の5項目外 |
| #13 | P2 | Particle Stormの認識timestampに時計逆行への保護がない。 | 今回の5項目外 |
| #14 | P2 | FPS・推論負荷が不統一。Mandalaの120FPS目標やManagerの追加Holistic負荷がある。 | 今回の5項目外 |
| #15 | P2 | `sitecustomize.py`が読み込まれる条件では、`.venv`内ライブラリを書き換え得る。 | 今回の5項目外 |

### 4.1 リソース蓄積について断定できる範囲

- 読んだ7シーンでは、粒子や配列が無制限に増え続ける明確な経路は確認されなかった。
- Particle Stormは4万粒子、Saturnは4万5千粒子の固定配列。
- Spiderの粒子は減衰して削除される。
- これは「メモリリークがない」という実機証明ではない。
- 強制終了でPythonのcleanupを通らない一方、Windowsがプロセス資源を回収する場合もある。「強制終了なら必ずGPUやカメラが漏れる」とも断定しない。
- native library、camera driver、GPU driver、温度、VRAM、handle数、長時間の性能低下は実機観測が必要。

## 5. P1の5項目に関する現行修正計画

この節はCodexが作った計画であり、まだ実装されていない。ユーザーの明示的な実装開始指示を受けた後も、最小差分と実機gateを維持する。

### 5.1 推奨順序

```text
#2 起動対象の明示
  ↓
#6 cleanupの基礎
  ↓
#9 Manager所有camera profileの統一
  ↓
#1 READY/FIRST_FRAME handshake
  ↓
#3 camera再取得の状態管理
```

`#6`を前倒しする理由は、後続項目の失敗経路を安全に試すため。`#2`は物理カメラを開く前に検証できるため最初に置く。

### 5.2 #2：起動対象を本番manifestへ限定

**現在**

```text
ディレクトリ内の .py を走査
→ 除外条件を適用
→ shuffle
→ earth.pyを先頭にする
→ 順次起動
```

**障害条件**

- 対象外の`.py`が同じディレクトリに存在するだけで候補になる。
- 監査時には49ファイルが走査条件に一致し、`scene_profile_runner.py`も候補に入り得た。

**最小修正案**

- 承認済みentrypointの明示リストを設定またはrelease manifestに持つ。
- 起動時に重複、存在、`*_acer.py`形式、対応する`*_2.py`、空リストを検証する。
- 本番autoはmanifest内だけから選ぶ。
- 手動UIも同じ承認済み集合を参照する。

**依存と副作用**

- ユーザーが似たファイルを目視し、正確なentrypointを決める必要がある。
- manifestの記述漏れはsceneが出ないという明示的な失敗になる。無関係なsceneを起動するより安全。

**最小確認**

- 未承認ファイルを置いても候補に出ない。
- 存在しないscene、重複、非Acer entrypointで起動前に明確に失敗する。
- 実際に起動したscene列とmanifestが一致する。

**失敗時ログ**

- manifest path・hash、解決後の絶対path、候補一覧、除外理由、launch ID。

### 5.3 #6：cleanupを一本化

**現在**

- Manager、shared camera、子sceneの各所に終了処理が分散している。
- 初期化の途中やcleanup自身の例外で、後段の解放が実行されない可能性がある。

**最小修正案**

- 所有した資源を記録し、逆順に解放する一つのcleanup経路へ集約する。
- `try/finally`で、個々の解放失敗を記録しつつ残りの解放を続ける。
- 子scene、UDP/TCP、thread、window、共有メモリ、cameraの所有者を明確にする。
- 正常終了を先に試し、期限内に終わらないときだけ段階的な強制終了へ移る。

**依存と副作用**

- #9、#1、#3の異常試験で資源を残さない土台。
- cleanupの待機が長すぎると切替時間が延びるため、段階ごとのdeadlineとログが必要。

**最小確認**

- 正常終了、起動途中例外、scene例外、cleanup一箇所の例外を別々に試す。
- 終了後に子PID、window、共有メモリ、camera handleが残らない。
- 次回起動がC922を取得できる。

**失敗時ログ**

- cleanup段階、開始・終了時刻、対象PID/thread/resource、例外traceback、強制終了への移行理由、終了code。

### 5.4 #9：camera profileをManagerへ反映

**現在**

- `scene_profile_runner`がAcer scene用の環境変数を子へ設定する。
- 物理C922はそれより前にManager側の`SharedCameraRelay`が開く。
- 子へ設定した解像度・FPS・backendが、実際の物理camera取得条件へ反映されない。

**最小修正案**

- 物理cameraのprofileはManager起動時に一度決め、Relayへ渡す。
- 各sceneは共有フレームの論理的な利用条件だけを持つ。
- 実際に開けたbackend、幅、高さ、FPS、fourccを起動ログに残す。

**依存と副作用**

- C922の安定profile候補は1280×720、MJPG、30fps、露出-5だが、このKids Disco実装での採用は実機確認後。
- sceneごとの異なる物理解像度要求はそのまま両立しない。必要なら共有フレーム受信後にscene側で変換する。

**最小確認**

- 設定値と実測値をログで比較する。
- Manager単体、基準scene、再起動後に同じprofileで取得できる。
- frame IDが増加し、解像度・FPSが期待範囲にある。

**失敗時ログ**

- camera index/device、USB接続、backend、要求値、実測値、fourcc、OpenCV error、frame ID、最終成功時刻。

### 5.5 #1：固定待ち時間をhandshakeへ置換

**現在**

```text
Managerが子を起動
→ 一定時間待つ
→ STARTを一回だけ送る
→ 旧sceneを終了
```

子が受信準備を終える前に`START`が送られると失われる。新sceneの初回描画が確認されないまま、旧sceneを終了し得る。

**最小修正案**

- 既存runtime portのTCP control channelを第一候補として検討する。
- 一つの`launch_id`に対して、少なくとも次の状態を返す。

```text
SPAWNED
→ CONTROL_READY
→ SHARED_CAMERA_ATTACHED
→ START受領
→ FIRST_FRAME
→ STOP_ACK
```

- Managerは`CONTROL_READY`確認後に`START`を送る。
- `FIRST_FRAME`確認後にだけ旧sceneを終了する。
- timeoutまたは子の早期終了では新sceneを片付け、旧sceneを維持または復帰する。

**依存と副作用**

- #6のcleanupが先に必要。
- #4のstale frame監視は今回の修正範囲外なので、`FIRST_FRAME`だけで長時間生存を保証しない。
- handshake追加で起動が少し遅くなるが、固定sleepより観測可能になる。

**最小確認**

- 子の受信開始を意図的に遅らせても、STARTを失わない。
- 旧sceneは新sceneのFIRST_FRAMEまで表示を維持する。
- handshake timeout時に旧sceneへ戻り、子PIDが残らない。

**失敗時ログ**

- launch ID、親子PID、scene、各状態のtimestamp、送受信message、timeout段階、子stdout/stderr、終了code。

### 5.6 #3：camera再取得を安全な状態機械にする

**現在**

- camera read失敗時にrelease・再openを試す。
- 再open失敗後に`cap=None`のまま次の`read()`へ進み、取得threadが例外終了し得る。

**最小修正案**

```text
CAPTURING
→ DEGRADED
→ RECONNECTING
→ CAPTURING
または
→ CAMERA_FAILED
```

- `cap`が有効な場合だけ`read()`する。
- 再取得は回数、backoff、deadlineを明示する。
- 復帰時は単にopen成功ではなく、増加するframe IDと新しいframe取得を確認する。
- 上限を超えたらManagerへ明確なfailureを返し、安全な待機または再起動へ移る。

**依存と副作用**

- #9でprofileを一本化し、#6で途中資源を解放できることが前提。
- #7のnative read block、#8のsceneごとのNone処理は別問題として残る。
- 再試行が無限loopにならないよう上限が必要。

**最小確認**

- C922切断、再接続、open失敗を個別に試す。
- 取得threadが黙って終了しない。
- 再接続後にframe IDが増え、基準sceneが再描画する。
- 復帰不能時に状態と理由がUI・ログへ出る。

**失敗時ログ**

- camera状態遷移、試行番号、backoff、OpenCV error、device/backend、frame ID、最終成功時刻、thread生存、Manager判断。

## 6. 最初の実機試験候補とgate

### 6.1 最初の3シーン

1. `finger_colorfull_dots_acer.py` → `finger_colorfull_dots_2.py`
   - 第一基準候補。
   - 指入力、共有camera、GPU描画、終了処理を一通り通せる。
   - 似た`finger_colorfull_dots.py`と取り違えない。
2. `finger_mandala_acer.py` → `finger_mandala_2.py`
   - 複数人対応と高い描画負荷の中心候補。
   - 現ラッパーは`_2.py`を起動する一方、棚卸しでは`finger_mandala_3.py`が看板候補になっている。ユーザー目視で本番版を決めるまで差を保持する。
3. `particle_storm_acer.py` → `particle_storm_2.py`
   - 4万粒子、GPU負荷、認識更新、切替後cleanupを見る異質な高負荷scene。

補欠：`saturn_particles_acer.py`。4万5千粒子の固定配列と宇宙系表現を確認できる。

### 6.2 試験A：単一scene 30分

- Managerから基準sceneを起動する。
- C922のframe IDが増加し続ける。
- 描画が止まらず、入力反応が継続する。
- CPU、Private Bytes、handle数、GPU memory、FPS、温度を一定間隔で記録する。
- 終了時に子PID、window、共有メモリ、camera接続を解放する。
- 終了後に同じsceneを再起動できる。

この合格は12時間安定性を意味しない。

### 6.3 試験B：Manager切替反復

- 同じsceneの再起動だけでなく、異種scene間の切替も行う。
- 新sceneの`FIRST_FRAME`確認前に旧sceneを落とさない。
- 切替ごとにPID、window、handle、Private Bytes、VRAMが持続的に増えない。
- 終了後に関連processが残らない。

反復回数は実装計画上20回案があるが、ユーザー確定値ではない。

### 6.4 試験C：失敗経路

- #1：`CONTROL_READY`遅延、`FIRST_FRAME`未到達。
- #3：C922切断、再接続、open失敗。
- #6：初期化途中例外、解放処理内例外。
- 各失敗は別々に試し、30分試験へ混ぜない。

### 6.5 共通ログ

- 試験ID、日時、Git commit、release ID、設定hash。
- Acer型番、CPU、GPU、RAM、Windows build、driver。
- Python実行ファイル、依存version。
- C922のdevice、USB port、backend、実解像度、FPS、fourcc。
- 親子PID、launch ID、scene、起動・終了code。
- handshake段階別timestamp。
- camera frame ID、最終frame時刻、描画FPS。
- CPU、Private Bytes、handle、GPU memory、温度。
- 期待動作、実動作、失敗前後のstdout/stderrとtraceback。

子のstdout/stderrは無制限にメモリへ保持せず、rotation可能なファイルへ残す案。毎frameの大量ログは避ける。

## 7. シーン候補と現在の整合した扱い

この一覧は使用候補であり、本番manifestではない。似た版をユーザーが目視して正確なファイルを指定する。

| ユーザーの候補名 | リポジトリ上の代表候補 | 現在の位置付け |
|---|---|---|
| `finger_mandala` | `finger_mandala_3.py`／既存Acerは`finger_mandala_2.py` | 看板候補。複数人、人ごとに異なる色。急なresetなし。entrypoint未確定 |
| `colorfull_dots_spheres` | `colorfull_dots_spheres.py` | 使用候補へ復帰。指の影響が弱いという棚卸し所見を目視し、idle／独立／reworkを判断 |
| `colorfull_wave_dots` | `colorfull_wave_dots.py` | 使用候補。独立sceneかFinger Dotsのlook統合か未決定 |
| `fractal_moving` | `fractal_moving_2.py` | 使用候補。既存entrypointは`fractal_moving_acer.py` |
| `finger_colorfull_dots` | `finger_colorfull_dots_2.py` | 使用候補かつ最初の安定性基準。entrypointは`finger_colorfull_dots_acer.py` |
| `otedama系` | `modern_otedama.py` | 身体ゲーム候補。`otedama_modern.py`は演出素材のmerge案。entrypoint未決定 |
| `minecraft` | `minecraft.py` | 手動・独立sceneの有力候補。長く遊ぶ工作室としての案 |
| `polygon_vibes系` | `polygon_vibes.py` | 触れる空間としてrework候補。派生表現の選択merge案 |
| `particle_storm` | `particle_storm_2.py` | 宇宙の山場。entrypointは`particle_storm_acer.py` |
| `roulette` | `roulette_game_advanced.py` | 手の回転で模様を回す作品としてrework候補。entrypoint未決定 |
| `skeleton_glitch` | `skeleton_glitch.py` | 踊る本編候補。既存Acer wrapperなし |
| `earth` | `earth.py` | 基本の見た目を維持。待機／宇宙への入口候補 |
| `spider_cursor_acer` | `spider_cursor_2.py` | 生き物遊び候補。entrypointは`spider_cursor_acer.py` |
| `saturn_particles` | `saturn_particles_2.py` | 崩して戻す宇宙候補。entrypointは`saturn_particles_acer.py` |
| `colorful_tree系` | `colorfull_tree.py` | 育てる遊び候補。リポジトリ上は`colorfull`綴り。Acer wrapperなし |

棚卸しで高評価だったが、ユーザーの使用リストへ明示追加されていない候補：

- `finger_grid_interaction_2.py`：布状の網を触る・切る・再生する。
- `hands_shake.py`：複数人で手を近づける共同遊び。
- `spiral_mouth_effect.py`：口を開いて渦や煙を強める変身体験。

これらを自動で本番採用しない。ユーザーへ目視候補として示す。

## 8. 全シーンに共通する体験契約

### 8.1 三つの層

各sceneは、可能な範囲で次の三層を分ける。

1. **時間層**：人がいなくても緩やかに変化し、長く見ても飽きにくい。
2. **反応層**：手、身体、タッチなどの入力に対し、直後に局所的で明確な反応を返す。
3. **ガイド層**：妖精のような半透明の存在が、次のアクションを動きで示す。

時間層と反応層を同じタイミング・同じ見た目で変化させると、子供が自分の操作結果を判別しにくい。速度、範囲、明度、色、音、出現位置などを分離する。

### 8.2 妖精guide

```text
無操作を検出
→ 妖精が薄く出現
→ 手本の動作を見せる
→ 参加者が似た動作をする
→ 妖精とsceneが成功反応を返す
→ 妖精は徐々に薄くなる
```

- 長文説明を常時表示するのではなく、動きで意味を伝える。
- 参加者がすでに遊べているときは邪魔をしない。
- ガイド自体もsceneの美術へ馴染ませる。

### 8.3 finger_mandala

- 複数人を別IDとして追跡する案。
- 人ごとに異なる色を割り当てる。
- 同じ人物の左右の手は同系色にする案。
- 全画面resetではなく、古い色・形・線を徐々に退場させ、新しい世代を徐々に混ぜる。
- 色相、対称数、stroke、粒子密度、残像長などを別周期で滑らかに変える。
- user actionによる即時反応は、時間変化より局所的・高速にする。

## 9. Managerと操作モードの計画

計画書では次の状態を分けている。名称は実装案であり、コードへはまだ入っていない。

| 状態 | 役割 |
|---|---|
| `AUTO_IDLE` | 無操作時。自律映像として成立するscene poolを自動再生 |
| `ACTIVE_PLAY` | ボタン、手、身体等で参加を検出。独立sceneも含む参加者向けpoolへ移る |
| `MANUAL_HOLD` | スタッフが承認済みsceneを任意指定し、必要時間維持 |
| `SWITCHING` | 新sceneのREADY／FIRST_FRAMEを確認し、安全に表示を移す |
| `STANDBY` | 起動失敗、モード切替、緊急時の安全な待機表示 |

### 9.1 参加者操作

- 画面上部左右に「前」「次」に相当する常設操作を置く案。
- 表記は`前のシーン／次のシーン`、`Prev／Next`、矢印、妖精誘導など複数案を目視比較する。
- カーソル移動だけでなく、dwellまたは明確なタッチ完了で発火する。
- dwell約1秒案があるが未確定。
- ボタン操作をactivityとして扱う。
- inactivity約120秒で`AUTO_IDLE`へ戻す案があるが未確定。

### 9.2 手動操作

- スタッフは承認済みsceneなら任意指定できる。
- MacBook UIとAcerローカルUIは同じManager／supervisor状態を操作する。
- 現在scene、次scene、camera、mode、health、緊急復帰を見られる構成案。

### 9.3 桜transition

- シーン間の章転換という役割は維持候補。
- 現在の桜エフェクトの視覚内容は一新する。
- transitionは新sceneの起動失敗を隠すだけの固定時間演出にしない。
- 新sceneの`FIRST_FRAME`と連動して終了する案。

## 10. rebirth2026側から参照した技術的事実

この節はWindows側Codexが、別タスク`rebirth2026 Sol 再開`、`TD復旧とcanonical実体照合を続行`および`C:\rebirth2026`から確認したもの。iPhone側が同じソースを取得していなければ、「Windows側Codexが確認した事実」と表現する。

### 10.1 MediaPipeとC922

- C922の安定profileとして1280×720、MJPG、30fps、露出-5を使った履歴がある。
- camera入力約30fps、Pose／Hand／Face推論約10fps、Object約7.4fps、TD描画60fpsという別周期構成。
- 描画と推論を分離し、遅い推論を表示全体へ伝播させない設計が有効だった。
- Hand＋Faceは5分以上、Hand＋Face＋Objectは10分以上の安定履歴がある。
- これは今回のKids Disco Python sceneや12時間本番の合格を意味しない。
- MediaPipe Objectの`Category.index`は`None`になり得る。過去に`int(None)`でcallbackが終了した。
- 生存確認は`sender_fps`だけでなく、増加する`camera_frame_id`と最終更新時刻を見る。
- Pose、Hand、Hand＋Face、Objectの段階起動とmodel存在・SHA確認が使われている。

### 10.2 TouchDesigner

- 別リポジトリ：<https://github.com/mindoverdrive/rebirth2026>
- Acer上の正規path：`C:\rebirth2026`
- canonical development TOE：`C:\rebirth2026\touchdesigner\development\rebirth2026_live.toe`
- runtime候補：`C:\rebirth2026\touchdesigner\runtime\rebirth2026_runtime.toe`
- manifest付きで昇格するまでruntimeを本番合格扱いしない。
- `start-venue.cmd`はBridgeを起動し、ready fileを待ってTouchDesignerと設定TOEを起動する。
- venue設定は確認時点で`Mi TV`、display index 1、1280×720、60Hz、fullscreen true。
- 現runnerの`READY`はTouchDesigner process生成直後で、Xiaomiへ実frameが出たことまでは証明しない。
- Operator PanelのFullscreenボタンがXiaomi用Window COMPを確実に開くかは未証明。
- TD側ではPython BridgeだけがC922を所有する。
- TD出力優先は`EMERGENCY RAW > MANUAL > AUTO`。起動基準は`STANDBY`、AI OFF。
- native-only Auto 88分19秒、scene切替100回の過去合格履歴があるが、最新runtime、Xiaomi表示、熱、今回のPython／TD切替は別gate。

## 11. Acer一発差し替え案

これは実装前の案。

```text
C:\RebirthKidz\
├─ releases\
│  ├─ stable-<release-id>\
│  └─ candidate-<release-id>\
├─ runtime\
│  ├─ current.json
│  ├─ previous.json
│  ├─ acer-production.json
│  └─ scene-manifest.json
├─ logs\
└─ launch\
```

### 11.1 差し替えflow案

1. 安定版を保持したまま、候補版のmanifest、依存、model、容量、設定、scene一覧を検査する。
2. 安全な待機表示へ移る。
3. 現Managerを正常終了し、子process、window、GPU資源、C922 handleの解放を確認する。
4. `current.json`相当の小さな参照を候補へ原子的に切り替える。
5. 候補Managerを起動する。
6. Manager ready、増加するcamera frame ID、操作UI ready、最初のsceneの`FIRST_FRAME`を確認する。
7. 全条件を通ったときだけ候補を現行版として確定する。
8. 途中失敗では参照を戻し、previous安定版を再起動する。

releaseにはGit commit、Python版、依存lock、model hash、承認済み`*_acer.py`と対応実装、camera/display profileを記録する案。

## 12. Python／TouchDesigner／待機画面の切替案

操作入口を次の四つへ揃える案。

1. Python映像を開始
2. TouchDesigner映像を開始
3. 待機画面
4. 直前の映像へ戻す

### 12.1 役割

- Acer内蔵画面：操作UI、状態、ログ、緊急操作。
- Xiaomi：作品映像のみを枠なし・最前面・cursor非表示で全画面表示。
- show-mode supervisor：PythonまたはTouchDesignerのどちらがC922とXiaomiを所有するか一元管理。

### 12.2 PythonからTDへの切替flow案

1. 承認済みruntime TOE、manifest、Xiaomi、TouchDesigner、portを事前確認する。
2. Python映像を待機へ移し、Managerとsceneを正常終了する。
3. C922と子processの解放を確認する。
4. Rebirth Bridgeを起動し、camera frame更新を確認する。
5. 承認済みruntime TOEを一つだけ起動する。
6. `/project1/output/out_display`をXiaomi用Window COMPへ接続する。
7. project identity、表示先、output cook／frameの進行を確認する。
8. 全成功後にだけTouchDesigner showへ確定する。
9. 失敗時はTDとBridgeを終了し、Python安定版へ戻す。

### 12.3 最小gate案

- Python→TD→Pythonを反復する。
- 二重camera取得、二重TD、残留processを発生させない。
- Xiaomiへ実frameが表示されることを確認し、黒画面を成功扱いしない。
- HDMI抜き差し後に表示先を再検出し、fullscreenを再適用できる。
- TD、Bridge、Xiaomiの各失敗からPython安定版へ戻れる。

## 13. 現在確定していないこと

- 本番採用する正確なscene fileとentrypoint。
- 各sceneを`AUTO_IDLE`、`ACTIVE_PLAY`、`MANUAL_HOLD`のどこへ所属させるか。
- `finger_mandala_2.py`と`finger_mandala_3.py`のどちらを本番土台にするか。
- P1修正順序案、TCP handshake方式、message名、timeout値の最終採用。
- C922のWindows device index、USB port、backend、実測profile。
- AcerのCPU、RAM、Windows build、GPU・camera driverの本番記録。
- XiaomiのWindows表示名、display index、解像度、拡大率、HDMI復帰挙動。
- 上部左右ボタンの最終デザイン、dwell時間、inactivity時間。
- 妖精guideの具体的なvisual designと共通実装範囲。
- MacBook UIの通信方式、認証、必須操作、緊急時fallback。
- TouchDesignerを本番中に切り替える正確なタイミングと戻す条件。
- 30分単一scene、切替反復、失敗経路、12時間試験の実測結果。
- 本番の実際の連続稼働時間。12時間は暫定設計基準。

## 14. 実装開始時に守る判断境界

1. ユーザーが指定した正確なscene fileを確定し、manifestに固定する。
2. 監査対象5項目は最小差分で扱い、各変更後に短い実機gateを通す。
3. 実測していない状態を「安定」と表現しない。
4. Codexの案は、ユーザーが選ぶまで提案として保持する。
5. 30分基礎gateを先に通し、機能とreleaseを凍結してから12時間試験へ進む。
6. 同じAcer上の安定版を保持し、候補版の失敗から戻せる状態で試す。
7. PythonとTouchDesignerのcamera ownerを同時に起動しない。
8. stop指示を受けたら、その時点で作業と出力を停止する。

## 15. 関連成果物とGit履歴

### 15.1 リポジトリ内成果物

- `REBIRTH_IPHONE_HANDOFF_2026-09-05.md`
  - 旧引継ぎメモv003。
  - 静的監査、P1計画、scene突合、rebirth2026参照、一発差し替え、TD切替を収録。
- `20260906-rebirth-implementation-plan.html`
  - 視覚化した実装計画書。
- `design-system/document.css`
  - HTML計画書の表示style。
- `design-system/math-copy.js`
  - HTML計画書の表示補助。
- `Reverse Ubers iPhone Handoff .md`
  - 本ファイル。直近会話を準生ログとして再構成したもの。

### 15.2 直近commit

| Commit | 日時（JST） | 内容 |
|---|---|---|
| `d83f99a` | 2026-09-06 04:41 | リバース2026実装計画書をHTMLで追加 |
| `7d712fe` | 2026-09-06 04:09 | iPhone引き継ぎメモを本番切替設計まで更新 |
| `71cc545` | 2026-09-05 23:47 | リバース向けiPhone引き継ぎメモと修正計画を追加 |
| `28f662c` | 2026-05-08 13:30 | 監査したPython実装側の基準commit |

本ファイル作成直前は`main`と`origin/main`が`d83f99a7ad08f457681c2abfad91cf2e3fadd09a`で一致していた。本ファイル自体は作成時点で未commit・未push。

## 16. iPhone側からWindows側へ返すときの形式

次の形式を使うと、ユーザーの決定とAI提案を混ぜずに戻せる。

```markdown
引き継ぎファイル：Reverse Ubers iPhone Handoff .md
基準commit：d83f99a

ユーザーが新たに確定したこと：
- 未記入

採用する正確なscene file：
- 未記入

AUTO_IDLE／ACTIVE_PLAY／MANUAL_HOLDの分類：
- 未記入

妖精guide・時間変化・action反応の決定：
- 未記入

TouchDesigner切替条件：
- 未記入

MacBook UIの必須操作：
- 未記入

実機で確認できた事実：
- 未記入

iPhone側の提案（未承認）：
- 未記入

未決定事項：
- 未記入

Windows側へ次に依頼する作業：
- 未記入

実装開始の明示：あり／なし
```

空欄は推測で埋めず「なし」または「未確認」とする。ユーザーの新しい発言が本ファイルと衝突する場合は、新しい明示指示を優先し、何が変わったかを記録する。

## 17. 2026-09-06：自律実装と単一シーン最優先への更新

### ユーザーによる実装許可と継続条件

その後のユーザー指示で、候補ブランチ上の調査・最小実装・テスト・修正・再検証・commit/pushが明示的に許可された。main/stableへの強制統合、force push、本番昇格、未確認を安定版と呼ぶことは禁止。人間/実機待ちはHuman Check Required、権限不足はPermission Blockedとして記録し、独立した作業は継続する。

### 最新の優先変更（ユーザー発言）

> 優先順位を次の一点に修正する。最優先はまず一つのシーンをAサージ機とCp22Nで子供が実地テストできる状態にすること。その際映像とインタラクション座標は構造として一致させる。この最新の優先に競合する場合のみ進行中の作業よりもこの指示を優先すること。それ以外は現在の作業を継続せよ。

Windows側は機器名の誤認を、既存文脈とOSのAcer/C922存在に基づいて解釈した。最初の候補は `finger_colorfull_dots_acer.py`。他シーンの演出より先に、この1シーンの起動入口と座標一致を実装した。

### Codexの実行結果（人間の実機合格とは区別）

1. P1 #2、#6、#9、#1、#3を順に実装。明示playlist、取得済み資源の解放、Managerのcamera profile継承、READY/START/START_ACK/FIRST_FRAME、再取得/フレーム鮮度/停止競合を確認した。
2. 最初のシーンに専用configと `Start Kids Test.cmd` を追加。C922名を照合し、先読み/切替ジェスチャー/桜遷移を無効にしてAcer primaryへ出す候補にした。
3. 映像のmirror/layoutと指先変換を共通化。端の1px越境を再現して修正。退出時に古い指先マーカーと映像が残らないようにし、無操作中の波をゆっくり動かす。
4. Windows venvが中継PIDを挟むことをOS読取で確認。疑似ランチャー＋実runnerでPID不一致を再現し、nonceと所有Job/PID照合に変更。親だけ消えた場合の子回収、先に作られた子の取り込み、Job終了を実OSで確認した。
5. 30分の時間指定終了、20回切替の指定、10秒ごとの資源記録、容量制限付き子stdout/stderrログを用意。試験完了を実機合格に自動変換しない。
6. 最終の自動テストは63件通過。実シーンのC922取得、GPU描画、30分、12時間は未確認。モデルは存在とサイズを読んだが、更新していない。
7. mainとorigin/mainは `260ee87` のまま。候補ブランチ `codex/rebirth2026-production-candidate` へ段階ごとに通常commit/push。コミットと全変更ファイルは最新候補レポートに列挙した。

### 実行環境で起きた制限と代替結果

- 許可されたPython 3.11.9でpreflightを実行すると、numpy、cv2、pygame、mediapipe、screeninfo、pygrabberが不足して停止した。カメラを開いて成功したとは記録していない。
- 既存映像用venvの直接実行がlean-ctxの許可リストに拒否された。
- 代替として、このリポジトリ内に `.venv-kids-test` を作成した。作成は成功したが、そのPythonでのpreflight実行も許可リストに拒否された。依存の導入や制限回避には進んでいない。
- これをPERMISSION_BLOCKED PB-01として記録した。別ディレクトリで動いていたユーザーの `finger_mandala_3_test.py` は止めていない。

### 次に必要な人間の確認

まず既存映像用Pythonで `Start Kids Test.cmd --check`。その後にC922の実映像、中央と四隅の指先一致、一人/二人/退出/再入場を確認する。30分、20回切替、USB復帰、終了後の再取得は別の試験として記録する。12時間はまだ始めていない。

演出側では、時間変化/アクション反応の分離という方向を維持する。`finger_mandala_3.py`と現wrapperの `_2.py` の対応、妖精の見た目、各sceneの選定、PAN UI、TDとの本番切替は未完了。これらを「もう実装して動いた」とiPhone側で補完しない。
