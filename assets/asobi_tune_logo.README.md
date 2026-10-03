# あそびTUNE 転換ロゴ

2026-10-03、ユーザー選択済みの二段ロゴ「あそび / TUNE」を転換へ追加。既存ColonyとTOKYO ISLANDを保持し、出現重みを各既存ロゴの2倍にする指示による。

- Library ID: `libfile_88b05c0331cc8191b6fc5a3e18b5bc43`
- 入力ファイル: `asobi-tune-logo-option2-two-line-transparent-20261003.png`
- 制作repoでのファイル: `asobi_tune_logo.png`
- PNG、1448×1086、RGBA、1948418 bytes、alpha 0〜255
- SHA256: `86101a2b219fd10b9ba5aae64375d6a519ec589ca13dfb28644c13bf9869956e`

Library原本のバイトを変更せず保存。切り紙風の文字、ピンクU、虹色断片、内部の白い紙も図柄として保持。再描画・白地除去・色変更なし。元RGB/alphaで縦横比保持の縮小、画面の幅・高さ52%以内、中央配置・既存の浮遊・フェードを行う。

選択は交互固定から重み付きランダムへ変更。あそびTUNE:Colony:TOKYO ISLAND = 2:1:1（50%:25%:25%）。転換開始ごとに一度だけ抽選し、同一転換中は固定。連続して同じロゴになることがあり、有限回で厳密に半数になる保証ではない。読み込み失敗時は従来同様Colonyへフォールバックする。

実機投影は未確認。検証・切り戻しは `ASOBI_TUNE_LOGO_HANDOFF_20261003.md` を参照。
