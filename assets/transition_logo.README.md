# Transition logo

ユーザー提供の白黒グローブ形ロゴを基に、組み込み image_gen で清書した `transition_logo.png`。2026-09-07 のトランジション用素材。元の提出画像は変更せず `transition_logo_source.jpg` として保存した。

最初の透過生成はノイズが多く不採用。採用素材は白黒の清書版。表示時の色・フェード・動きは描画コードで与える。`KidzDisco Colony` の文字は画像に焼き込まず、書体から描画する。

採用素材の生成プロンプト（built-in mode）：

```text
Clean logo asset restoration ONLY. Faithfully reproduce the attached small logo at higher resolution. It is a flat black distorted globe grid with white windows and a white rounded square border, dark charcoal outside. Keep precisely this black-and-white composition, same silhouette and same window count. Sharp smooth vector-like edges, flat solid fills. Absolutely no distress, no texture, no noise, no scratches, no decoration, no photographic treatment. Square canvas, full logo visible with margin, no cropping. Keep black regions solid black and white regions solid white. This is for projection as a center logo. No transparency needed on this version.
```

生成画像なので元ロゴとのピクセル一致は保証しない。実機での見え方は Human Check Required。
