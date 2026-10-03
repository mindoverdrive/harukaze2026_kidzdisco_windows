# TokyoIsland2026 イベント準備ブランチ（現用反映済み）

2026-10-03、ユーザーが現用へのロゴ反映と `TokyoIsland2026` ブランチ作成を承認。

- 準備repo: `C:\Users\go\Documents\ChatGPT\New project`。現在branch: `TokyoIsland2026`。
- 基点: 本番候補41409b5。本番候補branchは41409b5のまま保持。
- ロゴ実装commit: `b376fc5674df8b92e2df09022866598384af052b`（検証済み2958d97の5ファイルだけをcherry-pick）。
- 露出−5を含む既存configと他の未追跡作業は保持。config SHA256: `2f563d484ce1d22c2ce812f27a2922b49379df77f206774ece6fa15954f0dd00`。既存差分は今回のcommitに含めていない。
- 通常の `Start Rebirth Production.cmd` → `scripts/launch_production.py` → `scripts/start_operator.py` はこのrepoを参照したまま。次回の通常起動から新ロゴが有効。起動ファイル・設定の変更なし。
- 反映前に関連本番Pythonプロセス不在を確認。実アプリの終了・再起動・カメラ・投影操作なし。
- 反映先から関連103テスト再実行: 成功103、失敗0、エラー0、skip0。仮想画面・モック・合成fixture。
- 反映先の隔離レンダラーでも採用見本①とのRGBピクセル一致、粒子解除開始の完全保持、解除終了の透明化を確認。旧2素材のhash保持もテストで確認。
- 実機の白縁・残像・動的な見え方は未確認。次回通常起動時に2転換以上、Next/Back、Safe/解除を目視する。
- バックアップ: `C:\Users\go\Documents\Codex\2026-10-03\task-2\logo-review\adoption-backup`。変更前2ファイル・新規3ファイルの不在記録・config hash・元statusを保存。全体reset/stashは使用していない。
- 退避テストログ: 同 `logo-review\adopted-validation.txt`。
- GitHubへのpush、PR、merge、新規remoteリポジトリ作成なし。今回は既存repo内のローカル準備branch。

切り戻す場合は、後続変更と競合しないことを確認してロゴcommit b376fc5の変更だけをrevertするか、バックアップの描画・テスト2ファイルだけを戻し、新規素材・素材READMEを外す。露出設定や未追跡作業を巻き戻さない。引き継ぎ文書は履歴として保持してよい。

以下は専用worktreeでの実装・検証時点の記録。現用未反映という過去記述は本節で更新済み。

# TOKYO ISLAND 偶数転換ロゴ変更

2026-10-03。ユーザーが原色・透過保持の見本①を選び、Re:birth側を置き換えることを承認。実装・ローカル検証のみ。本番起動先の切替、remote push、PR、mergeは未実施。

## 対象・保全

- 基準: `41409b5667688bc0b9af8ae67875bd94b1f79351`、`codex/rebirth2026-production-candidate`。
- 元repo: `C:\Users\go\Documents\ChatGPT\New project`。
- 専用worktree: `C:\Users\go\Documents\Codex\2026-10-03\task-2\tokyo-island-worktree`。
- 作業branch: `codex/tokyo-island-logo-20261003`。
- 元repoの露出設定差分−3→−5、未追跡文書・status_dashboardはそのまま保持。専用worktreeの設定は基準コミットの−3であり、現用設定の代替として無確認で起動しない。
- 元のRe:birth画像、Colony画像、旧白地除去関数を保全。Colony描画、Manager、Overlay、粒子、Next/Back/Safe、設定・起動ファイルの変更なし。

## 変更

`transition_branding.py` の偶数cycle素材を公式TOKYO ISLAND WebPへ変更。白地除去を通さずRGBとalphaを保持する。奇数Colony→偶数Tokyoの選択をcover開始時に固定し、同じ転換中のcover/hold/revealでは変えない。位置・縦横比・画面52%以内のサイズ・浮遊・フェード・読み込み失敗時のColonyフォールバックは維持。

変更ファイルは描画1、関連テスト1、公式素材1、素材由来README1、本引き継ぎ1の計5ファイル。取得元とhashは `assets/tokyo_island_2026_logo.README.md`。

## 検証

- ロゴ関連7テスト成功。6回の交互転換、転換中の選択保持、clip復元、公式RGB/alpha・白・半透明・フェード、旧2素材のhash不変、欠損時フォールバック。
- 転換全般、operator navigation/panel、scene switchの関連103テスト成功（skipなし）。仮想画面・モック・合成fixtureを使用。実カメラや本番投影アプリを起動していない。
- 隔離レンダラーで奇数Colony／偶数Tokyo／黒背景見本の静止画を出力。黒背景の偶数描画は採用見本①のRGB出力とピクセル一致。既存粒子解除の開始時は欠けなし、終了時は全画素が透明キーカラーになることを確認。
- `git diff --check` 成功。LF→CRLFのGit警告のみ。
- 実機投影、動画中の白縁・残像・見え方は未確認。ローカル成功を実機合格に読み替えない。

使用Pythonは元CMDと同じ既存 `.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe`（3.12.10、pygame-ce 2.5.7）。依存導入なし。テスト時のみ `SDL_VIDEODRIVER=dummy`、`SDL_AUDIODRIVER=dummy` を子プロセスに設定。`-I -B` を用い、専用worktreeのrootをsys.pathへ明示追加してunittest discoverを実行。対象patternは `test_transition_*.py`、`test_operator_navigation.py`、`test_operator_panel.py`、`test_scene_switch.py`。

静止プレビューと再生成scriptは制作repo外の専用調査フォルダ:
`C:\Users\go\Documents\Codex\2026-10-03\task-2\logo-review\tokyo-island\tokyo-island-implemented-preview.png`
同フォルダの `render_implemented.py`。

## 採用と戻し方

現用CMDは元repoを参照したままで、今回の変更はまだ本番に有効でない。採用する場合は本変更の5ファイルだけを現用候補へ反映し、元の露出−5などの既存差分を保持する。重複起動せず、正規終了を確認したタイミングで元の `Start Rebirth Production.cmd` を使う。起動先の無断変更はしない。

実機で2回以上転換、Next/Back一往復、Safe/解除、粒子解除、白い年数字・色・輪郭、デスクトップ露出と残像を目視確認する。

切り戻しは今回の描画・関連テストを基準41409b5版へ戻し、新しいWebP・README・本書のみを除く。旧画像は残っているため置き戻し不要。後続変更がある場合は今回差分だけを逆適用し、元repo全体のresetや設定上書きをしない。
