# Hand Drawing standalone development (2026-10-19)

Git save update (2026-10-20 JST): the user authorized committing this existing
implementation and its tests on `matahariland`, before the dependent Hand Shapes
scene and the MATAHARI presentation changes. The uncommitted statements below
describe the development checkpoint. Actual-camera verification remains
unperformed; this is not production validation or production registration.

## Scope and state

Development checkout: `C:\Users\go\Documents\Codex\2026-10-16\task\tokyo-island`.
Base: `matahariland`, `5bcc6c47b90ac990cc91c27697b1ad66711f403a`.
The initial checkout was clean; this extension preserves and expands the earlier uncommitted hand-drawing work. All changes remain uncommitted for review. The 19-scene production playlist and original production directories are unchanged. No running application was stopped.

## Eight independent drawing hands

Both left and right index fingers draw. Each hand chooses its own color with raised-finger counts 1 through 5: cyan, gold, pink, green and violet. Counts must remain stable for 180 ms. Other hands cannot alter that hand's selected color. The label beside each wrist shows its hand ID, side, selected count and assigned dissolve style. There is no global selected color and the previous left-swipe clear action has been removed.

A fist, missing hand, ambiguous match, input gap over 200 ms, or jump over 15% of the stage diagonal breaks that hand's stroke. Re-entry seeds a new stroke. Active markers follow every accepted input frame; line segments are sampled at at most 30 Hz per hand, keeping the last emitted point so skipped samples do not create gaps.

The model is configured for at most eight hands. This supports the intended four-person, two-hand interaction capacity; it does not detect four people or associate each pair of hands with one person.

## Shared tracking and gestures

`hand_drawing_tracking.HandTracks` assigns a unique random style from the unused eight styles on first arrival, including the first hand. Production randomness has no fixed seed. Tests/previews inject seeds for reproducibility. Continuing hands retain their track and style when detector order changes or several hands share a Left/Right label.

Correspondence uses palm positions, bounded velocity prediction, hand shape and global minimum-cost matching. Left/Right is a weak matching cue, not identity; changes to the reported side must persist for 180 ms. Missing reservations last 1.5 seconds. When all eight slots are reserved, an unmatched newcomer waits until a slot expires. An expired return is a new arrival and receives a fresh random available style.

Ambiguous assignments break drawing continuity. A fully overlapped pair of indistinguishable hands cannot be reliably identified; proximity-based reacquisition is not biometric identity. Fast crossings, large occlusions, lighting and hand-size extremes remain live-test concerns.

`hand_drawing_gestures` reuses `HandTracker.finger_up` after projecting landmarks into wrist-to-middle-MCP palm coordinates, retaining the upright TIP/PIP behavior while handling hand rotation. Thumb direction follows the mirrored side. Without a known side, the thumb is excluded conservatively and the other four fingers can still draw/select colors.

`display_utils.open_camera`, `prepare_camera_frame` and `normalized_to_stage` provide the existing shared-camera path, single mirror and letterbox mapping. `hand_focus_overlay.draw_cv2` supplies the same muted bones, palm frames and bright active-input markers used by Otedama, `finger_mandala_3.py` and `finger_grid_interaction_2.py`. The active drawing markers are the actual index points. Only one MediaPipe Hands detector is created.

## Eight dissolve styles and bounds

Every segment retains the style and hand ID from its creation, so later tracking changes cannot restyle old ink.

| Style | Disappearance |
| --- | --- |
| Particles | Line fragments separate into pale specks |
| Smoke | Soft mist expands and drifts upward |
| Drops | Droplets fall downward with acceleration |
| Rise | Thin light trails rise upward |
| Swirl | Artwork contracts and rotates around its own hand's drawing bounds |
| Wave | A traveling spatial wave bends the fading line |
| Shards | Small line fragments rotate and separate |
| Wipe | A pale front travels from the drawing's left edge and removes the line |

All effects hold for 3.5 seconds then fade over 3 seconds. Intensity varies smoothly without rapid flashing. The default global history cap is 1920 segments, enough for eight hands sampled at 30 Hz throughout the 6.5-second lifetime. A manually reduced cap may evict the oldest segments earlier.

All styles share fixed image buffers, including quarter-resolution mist/glow buffers. At most 96 emitting segments produce two wisps each (192 wisps total), shared across fading hands. Particle positions are derived from age; no persistent particle list grows. Tracking/color/position state is bounded to eight reserved hands. Expired lines and absent reservations are removed.

## Standalone lifecycle and run

The resizable 960 x 540 preview stays within the primary monitor, independent of the production offset. `--fullscreen` is opt-in. Q, Escape and window close request exit. Unavailable cameras give a clear error; failed reads still poll exit controls. Repeated shared-frame IDs do not infer or append ink again. Cached hand feedback clears after 250 ms; continuing read failure exits after one second. Camera/model/window resources close on normal exit and exceptions.

The same runner supports the separate `hand_shapes_app.py` scene, including gap notifications and retired-shape fading. No production wrapper or NEXT/BACK registration is added.

Use the existing Windows Python when the camera and monitor are available for testing:

```powershell
Set-Location 'C:\Users\go\Documents\Codex\2026-10-16\task\tokyo-island'
& 'C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe' -B .\hand_drawing_app.py
```

Timing/history flags: `--hold-seconds 3.5 --fade-seconds 3 --max-segments 1920 --color-stable-ms 180`.
The palette is `FINGER_COLORS_BGR` in `hand_drawing_gestures.py`; visual constants are in `hand_drawing_effects.py`. No dependencies were installed.

## Verification and synthetic previews

Final combined result: **92 tests passed in 2.076 seconds**: 36 drawing/input/lifecycle tests, 18 effects tests, 18 tracking tests, 4 existing common-overlay tests and 16 new shape-scene tests. The drawing/shared subset independently passed all 76 tests. `git diff --check` passed; the Git index is empty, the production configuration has no diff and HEAD remains the base commit above.

Tests include eight simultaneous hands, repeated side labels, changed detector order, crossings/ambiguity, short absence/re-entry, expired reservations, unique initial random styles, independent color stabilization, rotated poses, sustained eight-hand 60-FPS input for eight seconds, all-style expiry, global history/particle bounds and camera/window cleanup.

Render-only timing at 960 x 540: a synthetic eight-hand/30-Hz history of 1560 segments (712 fading) had median 14.09 ms and p95 14.76 ms; 1920 simultaneously fading mixed-style segments had median 20.94 ms and p95 22.03 ms. These measurements exclude camera capture, MediaPipe inference, tracking, GUI presentation and shape rendering, so they are not an end-to-end FPS claim.

The installed native MediaPipe model successfully initialized with `max_num_hands=8`, processed a blank synthetic RGB frame and closed. This confirms that setting works in the existing environment; it is not evidence of detecting eight real hands.

Reproduce focused tests:

```powershell
$env:TEMP='C:\Users\go\Documents\Codex\2026-10-16\task\tmp'
$env:TMP=$env:TEMP
$env:PYTHONPATH='tests;.'
$env:SDL_VIDEODRIVER='dummy'
$env:SDL_AUDIODRIVER='dummy'
& 'C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe' -B -c "import cv2,numpy,pygame; import unittest; s=unittest.defaultTestLoader.loadTestsFromNames(['test_hand_drawing_app','test_hand_drawing_effects','test_hand_drawing_tracking','test_hand_focus_overlay','test_hand_shapes_app']); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful())"
```

Artifacts outside Git in `..\artifacts\hand-drawing-eight`:

- `eight_hand_drawing_synthetic.gif`: actual controller and renderer, eight hands, independent colors and styles, shuffled detection order, complete disappearance.
- `eight_hand_drawing_timeline.png`: drawing, dissolving and empty states.
- `eight_styles_synthetic.gif` and `eight_styles_50.png`: same-color/same-shape comparison of all eight effects.

These previews are explicitly labeled synthetic input and contain no camera imagery. The earlier single-hand preview remains historical; the eight-hand previews supersede it for this extension.

## Remaining live checks

Actual four-person recognition, eight simultaneously visible hands, stable identity through physical overlap, finger/side recognition under venue lighting, physical-camera alignment, participant spacing, total capture/inference/render latency, monitor placement, camera reconnect and manual exit are unverified. No real camera was opened and no live app was stopped. Automated camera/model/GUI tests use mocks; the separate native-model check uses a generated blank image. See `HAND_SHAPES_DEVELOPMENT_20261019.md` for the new scene's separate behavior and verification.
