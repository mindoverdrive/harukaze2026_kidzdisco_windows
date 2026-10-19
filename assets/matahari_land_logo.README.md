# MATAHARI LAND transition artwork

Confirmed by the user on 2026-10-20 JST: the existing brown unified transparent
version, `MATAHARI-LAND-unified-transparent.png`.

- Library source: `libfile_848de5694db081918822ec6de9936beb` (version 0).
- Original file ID: `file_000000009dbc81f690a9ecc8054745d2`.
- Runtime copy: `matahari_land_logo.png`, copied byte for byte; no new design.
- PNG RGBA, 1254 x 1254, 379646 bytes.
- SHA-256: `ce45dc404444163a5ba199c1dc16abc0123e018e243f905462fc6277bcef0eeb`.

`transition_branding.py` uses the existing size fit, drift, fade and panel clips.
For dark-background contrast, a separate pale rounded backing is drawn behind
the visible alpha bounds. Source RGB, per-pixel alpha and file bytes are retained.
The backing fades and is clipped together with the artwork; it never clears the
opaque transition cover.

This replaces only the Tokyo Island event slot. Colony/Kidz Disco and Asobi Tune
slots, source assets and weights (1:1:2) are preserved. The original Re:birth and
Tokyo Island assets remain available. No production configuration is changed.
