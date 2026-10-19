# MATAHARI LAND preparation review (2026-10-20 JST)

## Git save authorization and recheck (2026-10-20 JST)

The user subsequently authorized ordinary commit/push to `origin/matahariland`.
The review/pending-approval statements below describe the preceding checkpoint.
The save is grouped into four units: existing eight-hand drawing foundations,
dependent Hand Shapes, the accepted MATAHARI transition logo, and per-hand color
guidance plus this review record. Generated previews/videos, backups and temporary
tools remain outside Git. No new implementation or production entry is added.

The remote was fetched before saving and matched local base `5bcc6c4`, with no
remote-only commits. The same 250 related tests were rerun as the normal Windows
user: 249 passed immediately; the fixture scene-switch test encountered Windows
Access Denied (`WinError 5`) once and passed its single isolated retry (five
fixture switches, startup/cleanup). This intermittent fixture result is retained
in the record rather than treated as proof of stable production operation.
Logs are in `..\artifacts\matahari-git-save-20261020\tests.txt` and
`scene-switch-retry.txt`. Difference checks passed.

**Actual camera verification remains unperformed. No production validation is
claimed.** Excluding sci-fi jacket from the production rotation remains the next
change: its source and the current 19-scene production configuration are untouched
in this save. No force push, merge or repository visibility change is authorized.

## Scope and protection

Checkout: `C:\Users\go\Documents\Codex\2026-10-16\task\tokyo-island`.
Branch/base: `matahariland`, `5bcc6c47b90ac990cc91c27697b1ad66711f403a`.

At entry, 11 hand-drawing/shape files were already uncommitted. Their original
bytes and SHA-256 hashes, the working patch, Git status and HEAD were saved in
`..\artifacts\matahari-prep-backup-20261020-044654`. The additional branding and
preview test originals were also copied there. No stash/reset was used.

Only the two requested presentation changes were made. Of the original 11 dirty
files, only `hand_drawing_app.py` changed in this task, and its incremental change
is limited to the rendering import and guidance call. Original tracking, gesture,
eight dissolve effects, shape scene and four uncommitted test files retain their
entry hashes. Their previous development notes are unchanged.

## Event logo

The current checkout and existing local work records had no MATAHARI asset.
Library contained two earlier files. The user explicitly selected
`MATAHARI-LAND-unified-transparent.png` (brown, unified transparent version) on
2026-10-20 JST. It was copied byte for byte to `assets/matahari_land_logo.png`.
Provenance and the SHA-256 are in `assets/matahari_land_logo.README.md`.

The Tokyo Island event slot is now `matahari_land`. Its probability remains 1/4;
Colony/Kidz Disco remains 1/4 and Asobi Tune remains 1/2. A choice is latched for
the entire covering/covered/revealing cycle. Size fit, drift, fade, panel clip,
opaque curtain and unavailable-asset fallback retain the existing behavior.

The accepted brown ink is dark on black. A separate pale rounded backing behind
the visible ink provides contrast; it fades/clips together with the logo. The
source RGB, alpha and geometry are not recolored or regenerated. Colony/Kidz
Disco and Asobi source bytes and rendering remain unchanged. The historical
Re:birth source and Tokyo Island source also remain unchanged; this task does
not reinstate the older Re:birth slot, which was already inactive at entry.

The existing manual preview now selects and labels MATAHARI LAND. Its historical
CMD filename is retained; no launcher target or production setting is changed.

## Per-hand color guidance

`hand_drawing_feedback.py` draws presentation only:

- A small color chip and larger number beside each wrist, using that hand's
  stabilized selected count and the existing `FINGER_COLORS_BGR` mapping.
- The compact track ID and stabilized L/R side make the association explicit
  when people or the detector share the same handedness label.
- An illustrated one-to-five finger/color key in the lower-left corner.
- Deterministic placement in track-ID order. Labels avoid one another, active
  drawing markers, the existing NEXT/BACK regions and the corner key. Short
  connector lines are also omitted where they would cross protected regions.

The number is the confirmed count that actually selects the ink color, retaining
the existing 180 ms stabilization and fist/absence color retention. No gesture,
identity, stroke sampling, effect assignment, camera or navigation rule changed.
The old verbose dissolve-style labels and top-left color dots were replaced.

This drawing scene is still standalone. The production playlist remains the
existing 19 scenes. NEXT/BACK is shown only as the actual overlay renderer in the
synthetic composition to inspect spacing; this is not new scene registration.

## Changed files in this task

- `transition_branding.py`
- `scripts/preview_transition_logos.py`
- `assets/matahari_land_logo.png` (new, existing approved artwork)
- `assets/matahari_land_logo.README.md` (new provenance)
- `hand_drawing_app.py` (incremental rendering change over prior dirty work)
- `hand_drawing_feedback.py` (new presentation helper)
- `tests/test_hand_drawing_feedback.py` (new placement/palette tests)
- `tests/test_transition_branding.py`
- `tests/test_logo_preview.py`
- `tests/test_random_transition_effects.py`
- `MATAHARI_PREPARATION_REVIEW_20261020.md` (this record)

## Verification

**250 unique related tests passed, no skips.** The restricted initial run passed
240; 9 transition-manager socket tests and 1 fixture scene-switch test were denied
localhost access (`WinError 10013`). Only those 10 were retried as the normal
Windows user, all passing. No security setting or package was changed.

Coverage includes independent eight-hand color selection and tracking, detection
reordering, ambiguity/absence handling, all eight fade styles and bounded history,
existing shape-scene behavior and cleanup, new crowded-label layouts at 320x240
through 1920x1080, unchanged drawing-marker/navigation pixels, exact palette,
brand probabilities/cycle latching, asset hashes/RGB/alpha, dark backing and clip,
all 48 logo/effect combinations, cover/reveal/Safe behavior, NEXT/BACK and fixture
scene startup/switch/shutdown. GUI rendering uses SDL dummy; camera lifecycle
tests use mocks. The fixture manager owns and cleans up only its test children.

`git diff --check` passed (line-ending warnings only). Git index remains empty.
`configs/rebirth_operator_acer_xiaomi.json` has no diff. HEAD and branch remain
the entry values. No running user application was stopped; no production scene
was added, no dependency/environment update, commit, push or merge was performed.

Artifacts and reproduction scripts are outside the repository:

- `..\artifacts\matahari-prep-20261020\matahari_review.png`: review sheet.
- `transition_matahari_dark.png`: actual covered transition renderer.
- `transition_logos_dark.png`: all three retained/current slots on dark ground.
- `hand_drawing_eight_hands.png`: actual drawing controller/renderer with eight
  synthetic hands plus the existing navigation overlay surfaces.
- `preview-evidence.json`: 8 tracked hands, 8 badges, both sides and all 8 styles.
- `tests.txt`, `tests.json`, `tests-io-retry.txt`, `tests-final.json`: exact results.
- `hand-drawing-delta-from-start.patch`: this task's delta over prior dirty work.
- `..\tmp\verify_matahari_prep.py`, `retry_matahari_io.py`,
  `render_matahari_prep.py`: reproducible checks using the existing Python 3.12.10.

## Actual-camera verification and remaining checks

**Actual camera checks performed in this task: none.** No physical camera was
opened and no live camera images were captured. Synthetic landmarks test the
actual drawing/controller/rendering code; they do not validate real detection.

Still to check at the venue: projected brightness and backing appearance, label
and key readability at participant distance, real finger/side detection, eight
visible hands and occlusions under venue lighting, perceived label placement and
latency, and live NEXT/BACK/exit behavior. Production registration and commit/push
are pending the user's review, as requested. Work stops at this review state.
