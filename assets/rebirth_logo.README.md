# Re:birth transition identity

最新結果: 白抜き版をXiaomiへ表示し、ユーザーが「ok」と回答。白い四角/内部の白領域が抜けた基本目視を確認済み。全解除パターン・長時間耐久は別途未確認。

ユーザー提供の `rebirth_logo_source.jpg` をそのまま使用する。2026-09-07に「このロゴはいじらないこと」と明示されたため、生成した加工案は不採用・製品から参照しない。

原本SHA256: `3ab9a7e05f1c3a845a8131a6eb635d909304d138b25d4e351fbba5187543d6fc`

形、書体、ロゴと文字の位置関係を維持。最新指示「白背景はくりぬいて、黒部分だけが表示されるように」に従い、描画時だけ白背景と内部の白抜きをalphaに変換する。輪郭の白マットも除き、白い縁が残らないようにする。原本ファイルは変更しない。縦横比を保持した縮小、構成全体の位置移動とフェードを行う。文字を別フォントで打ち直さず、KidzDisco Colonyのタイトルと重ねない。

`transition_branding.py` が奇数cycleに従来Colony、偶数cycleに原本Re:birthを選ぶ。選択はcover開始で固定し、cover/hold/reveal途中では変えない。既存の遮蔽・シーン停止/起動・粒子分解の制御経路は維持。原本が読めない場合は従来Colonyへフォールバックする。

Mandala単独試験を維持して実装したため、この変更のXiaomi目視は未実施。Mandalaの目視結果を受けた後、navigation有効の試験で2回以上切り替え、ロゴと文字が交互に現れ、デスクトップが露出しないことを確認する。

Mandalaの外向き拡散＋色変化の目視OK後、旧単独試験をquit・プロセス不在確認し、`--audience --navigation --duration-minutes 30`で交互表示試験を起動。ログは `test_reports/rebirth_branding_20260907.stdout.log`。FractalのFIRST_FRAME=2.828秒。交互表示自体の目視判定は未確認。

白抜き追加後: 専用4試験で原本hash一致、内部/外部の白領域透過、暗い部分保持、clip復元、全面遮蔽alpha保持、交互表示とフォールバックを確認。全体3.12=475件/24skip、3.11=468件/70skipで失敗なし。描画プレビュー `test_reports/rebirth_cutout_preview.png` を確認。旧Manager/overlay正常終了後、`test_reports/rebirth_cutout_20260907.stdout.log`へ新版を起動。実機の白抜き/交互表示は目視待ち。
