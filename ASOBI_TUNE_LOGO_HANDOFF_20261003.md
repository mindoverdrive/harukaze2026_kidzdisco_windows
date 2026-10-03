# あそびTUNE追加・転換ロゴの重み付き選択

2026-10-03。ユーザーの「Tokyo Island2026ブランチに、切り替わりの際のロゴにこれも追加して、さらに出現確率は二倍にして」に従う。既存ColonyとTOKYO ISLANDを保持し、あそびTUNEを追加。以前の奇数Colony／偶数TOKYO ISLANDという固定交互方式は、この変更で重み付き抽選へ更新する。

## 実装

- 選択重み: あそびTUNE:Colony:TOKYO ISLAND = 2:1:1（50%:25%:25%）。各転換開始時に一度抽選し、cover/hold/revealと左右clipで同じ選択を保持。連続して同じロゴが出る場合があり、有限回で厳密な配分を保証しない。
- あそびTUNEとTOKYO ISLANDは元RGB・alphaで合成。白い紙、ピンクU、虹色断片、年数字を維持。元画像バイト変更、再描画、白地除去、色変更なし。サイズ制限・配置・浮遊・フェードは既存のカラー側と同じ。
- Colonyの画像・タイトル・描画を保持。Colonyの表示回数に応じて既存の文字／動きのバリエーションを進める。
- 素材欠損時は従来同様Colonyへフォールバック。Manager・Overlay・粒子・Next/Back/Safe・設定・通常起動入口は変更なし。
- 変更5ファイル: `transition_branding.py`、`tests/test_transition_branding.py`、`assets/asobi_tune_logo.png`、同素材README、本書。

## 素材

ユーザー選択済みLibrary `libfile_88b05c0331cc8191b6fc5a3e18b5bc43` の `asobi-tune-logo-option2-two-line-transparent-20261003.png` をこのWindowsの専用フォルダへmaterializeし、存在・実画像・読み込みを確認。1448×1086、RGBA、透過PNG。原本hash等は `assets/asobi_tune_logo.README.md`。

## 対象と保全

- 現用repo: `C:\Users\go\Documents\ChatGPT\New project`、対象branch `TokyoIsland2026`。
- 作業基点: `7b54bda88f1b5ab7b7986ea89c1cfe278c43bdb1`。
- 隔離worktree: `C:\Users\go\Documents\Codex\2026-10-03\task-2\asobi-tune-worktree`、検証branch `codex/asobi-tune-weighted-20261003`。
- 検証済み5ファイルだけを対象branchへ反映してローカルcommit。露出−5の未commit差分と既存未追跡作業を保持し、今回のcommitへ含めない。
- 現用configの保持hash: `2f563d484ce1d22c2ce812f27a2922b49379df77f206774ece6fa15954f0dd00`。
- 旧Re:birth、Colony、TOKYO ISLAND素材の原本を保持。反映前の描画・テストは `C:\Users\go\Documents\Codex\2026-10-03\task-2\logo-review\asobi-tune\adoption-backup` へ保存。
- 通常の `Start Rebirth Production.cmd` は同じ現用repoを参照したまま。実アプリを起動・終了・再起動していない。GitHubへのpushは今回未実施。

## 検証と次回確認

- ロゴ関連10テスト成功。2:1:1の抽選呼び出し、6転換で全ロゴと連続出現、同一転換固定、2000転換のseed付き割合確認、原色/alpha/白/半透明/フェード、Colony・旧Re:birthのhash保持、素材欠損時のfallback。
- 転換全般、operator navigation/panel、scene switch関連106テスト成功、skipなし。仮想画面・モック・合成fixtureを使用。
- 実コードの隔離描画で3ロゴを既存の転換背景上へ表示。粒子解除開始は欠けなし、終了は全画素が透明キーカラーになることを3ロゴとも確認。
- 静止プレビューは実際の頻度サンプルではなく各ロゴの表示例。素材・描画方法・配置は製品と同じ。実カメラ・実機投影・動的な白縁や残像は未確認。
- スクリプト／プレビュー／テストログは制作repo外の専用 `logo-review\asobi-tune` フォルダ。既存Python 3.12.10、pygame-ce 2.5.7を使用。依存導入なし。

次回通常起動時に、3ロゴの色・輪郭・透過、複数転換、Next/Back、Safe/解除、粒子解除とデスクトップ露出を目視確認する。少ない回数でちょうど2:1:1にならないことを不具合と扱わない。

切り戻しは今回の5ファイルだけを逆適用し、基点7b54bdaの2ロゴ交互方式へ戻す。後続変更があれば3者比較し、露出設定・未追跡作業・以前のTOKYO ISLAND導入を巻き戻さない。repo全体reset/stashは不要。
