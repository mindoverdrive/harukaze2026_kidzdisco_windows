# TOKYO ISLAND: Modern Otedama production adoption (2026-10-16)

## Base and scope

- Branch: `matahariland`, based on `TokyoIsland2026` commit `8a7c8d03b8f23d9ec97f0e12df4914bafcd8ee0c`.
- The Windows production checkout at `C:\Users\go\Documents\ChatGPT\New project` had this same HEAD. Its uncommitted `CAMERA_EXPOSURE=-5` setting and unrelated untracked files were left in place. The 2026-10-07 distribution copy has the same relevant source contents after normalizing line endings.
- `modern_otedama.py` is the existing representative Otedama candidate identified in `REBIRTH_IPHONE_HANDOFF_2026-09-05.md`. The other existing file, `otedama_modern.py`, was described there as material for a possible later effects merge. No new game or visual redesign was made.

## Change

- Added `modern_otedama_acer.py` as the standard scene profile entrypoint and registered it once, at the end of the explicit production playlist. The playlist now has 18 scenes. The trial `config.json` was not changed.
- The game now attaches to the Manager's shared camera once and fails clearly if it is unavailable. It reports FIRST_FRAME only after a processed camera frame is presented. A sustained camera read failure exits instead of displaying a stale fallback indefinitely.
- Esc and window close record the exit request. Scene cleanup releases MediaPipe and the shared camera on normal exit or runtime error, allowing Manager NEXT/BACK to use its existing stop and promotion path.

## Verification

- Focused Otedama tests: 4 passed with a synthetic camera and dummy SDL display. These cover unique registration, camera attach failure, frame presentation before startup acknowledgement, Esc, and resource release.
- Existing playlist (5), scene protocol (7), scene navigation (10), real fixture switching (10), exit observations (8), cleanup (8), operator navigation (7), and launcher (8) tests passed: 67 tests total including the new tests. Tests that spawn scene processes were run outside the restricted Windows sandbox after the sandbox blocked child process communication. No physical camera was used.
- `scripts/launch_production.py --check-only` reached the display check and stopped: expected audience `\\.\DISPLAY5`, detected only `\\.\DISPLAY1`. The current production display layout, Otedama hand interaction, NEXT/BACK on the real monitors, and final camera release therefore remain unverified on hardware.

## Camera background removal follow-up (2026-10-16)

- The confirmed display-removal scope is the camera image composited into the Pygame game background; this scene has no separate camera-preview window. Removed its resize/tint/alpha-surface pipeline and the now-unused NumPy import. Every draw now clears the stage with the existing `COLOR_BG_DARK = (5, 5, 10)`.
- Shared camera acquisition, mirrored RGB hand inference, palm colliders and their visible rings/skeleton, balls, particles, score, start/replay controls, the 90-second speed ramp, FIRST_FRAME acknowledgement, and cleanup remain in place. Logical rendering stays at 1280 x 720; screen-size adaptation remains pending below.
- Focused verification: all 16 tests passed (12 Otedama production tests and 4 hand-overlay tests). The added regression uses asymmetric colored and white synthetic frames to verify that camera pixels stay hidden, the input is still mirrored and converted correctly, palm collisions bounce the ball and score, the exact palm marker remains visible, and a missing frame clears stale hand feedback. Existing tests cover active timing, camera loss/recovery, startup acknowledgement, Esc, and resource release.
- Inspected a synthetic-input screenshot produced by the actual renderer: dark background, visible ball, hand skeleton, and palm collision circle. No physical camera or audience display was used. This narrow follow-up did not change Manager navigation; real-monitor NEXT/BACK and final camera release still require the on-site check.

## On-site check remaining

- **未完了・最終確認前に実施:** Otedamaシーンを、実際に使用する画面サイズに合わせる。2026-10-16の追加指示では後工程として指定されているため、Earth追加作業では画面サイズ調整を実装しない。使用画面の解像度・縦横比が確定した後、表示、カメラ座標、掌の衝突位置、開始ボタンの配置を合わせて確認する。
- **Camera background removal implemented and automatically verified:** Scope was confirmed on 2026-10-16 and implemented as described above. Visual quality and interaction on hardware remain part of final acceptance.

With the intended audience monitor and camera connected, use the production launcher, select Modern Otedama with NEXT/BACK, check that hands start and bounce the game, switch away and back, then exit from the operator panel. Confirm that the Manager and shared camera finish cleanly. Do not interrupt an event session to perform this check.
