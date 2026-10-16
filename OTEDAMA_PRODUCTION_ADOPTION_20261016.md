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

## On-site check remaining

With the intended audience monitor and camera connected, use the production launcher, select Modern Otedama with NEXT/BACK, check that hands start and bounce the game, switch away and back, then exit from the operator panel. Confirm that the Manager and shared camera finish cleanly. Do not interrupt an event session to perform this check.
