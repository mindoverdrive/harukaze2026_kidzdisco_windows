# TOKYO ISLAND 2026 転換ロゴ

2026-10-03、ユーザーが「① 原色＋透過を保持」を選択し、Re:birth側への差し替えを承認。

- 取得元: https://tokyoisland.tokyo/2026/wp-content/themes/tokyoisland_2026/images/common/logo/logo.webp
- 公式トップページ: https://tokyoisland.tokyo/
- 取得日: 2026-10-03
- ファイル: `tokyo_island_2026_logo.webp`（公式原本のバイトを変更せず保存）
- 寸法: 1560×1147、WebP、alphaあり、218008 bytes
- SHA256: `2aa13aec05387fa2b3280846da722f4201c87a996b26af1ea98e120492839068`

`transition_branding.py` が奇数cycleに既存Colony、偶数cycleに本素材を選択する。RGB・元alphaを保持した縦横比付き縮小と通常alpha合成を行い、旧Re:birth用の白地除去は行わない。白い年数字・飛行機等も図柄として保持。表示位置・フェード・サイズ制限は旧偶数側と同じ。読み込み失敗時はColonyへフォールバック。

元の `rebirth_logo_source.jpg`、README、白地除去関数は切り戻しのため保持。画像・文字の再描画、生成、色変更はしていない。公式サイトで公開されていることを再配布許諾の根拠とはしない。

実機投影の見え方は未確認。隔離レンダラーの静止画・関連ローカルテストは引き継ぎ文書を参照。
