# Hand Shapes standalone scene (2026-10-19)

Git save update (2026-10-20 JST): the user authorized committing this existing
scene and its tests after the shared hand-drawing implementation on
`matahariland`. The uncommitted statements below describe the development
checkpoint. Actual-camera verification remains unperformed; this is not
production validation or production registration.

## Scope

`hand_shapes_app.py` is a separate scene from Hand Drawing. It uses the shared tracking, finger-count stabilization, dissolve renderer and standalone camera/window lifecycle developed for the eight-hand drawing scene. Development remains on `matahariland` at base `5bcc6c47b90ac990cc91c27697b1ad66711f403a`, with all changes uncommitted. No production playlist entry, wrapper, commit or push is added.

## Interaction

| Raised fingers | Shape covering the hand |
| --- | --- |
| 1 | Circular ring with a direction mark |
| 2 | Pointed lens |
| 3 | Triangle |
| 4 | Square |
| 5 | Five-point star |
| 0 | Current shape dissolves after the count stabilizes |

Each hand has its own 180 ms count stabilizer. The shape changes with the count; the randomly assigned dissolve style does not. Current shapes have a faint translucent fill and a luminous outline so the detected hand remains visible beneath them.

All 21 landmarks use the scene's shared stage/letterbox mapping. The wrist-to-middle-MCP direction defines the hand's orientation. The outline encloses the projected hand points, follows position and angle with a short time-based smoothing interval, grows immediately when necessary, and shrinks gently. The bright common input marker is the palm point used to calculate the shape basis. Shared gesture counting operates in palm-local coordinates, so rotating the hand does not by itself change the count.

Both hands are accepted, up to eight at once. The shared tracker gives every reserved hand a different random style from the first arrival, preserves it across detector-order changes and short absence, and releases a missing slot after 1.5 seconds. This tracks hands; it does not identify four people or pair hands by person. Fully overlapping indistinguishable hands remain ambiguous. See `HAND_DRAWING_DEVELOPMENT_20261019.md` for matching and capacity details.

## Shape changes, disappearance and bounds

Only a count change, a stable fist or loss of a visible hand retires the old outline into the dissolve renderer. Moving the same shape does not add an outline every frame. A retired outline keeps its hand ID, color and assigned style. Repeated missing frames do not retire it again. Short re-entry keeps the style reservation and restarts position smoothing.

There are at most eight current shapes and eight tracking/count records. Retired outlines share the existing globally capped history of 1920 segments, 192 wisps and fixed dissolve buffers. The current-shape renderer uses one shared temporary tint surface for all hands. Default retired-shape hold time is zero and fade time is three seconds. Each retired outline disappears completely; frequent count changes cannot grow history without bound. A deliberately smaller history cap may remove old residues earlier.

## Start

Use the existing Python environment when the camera and monitor are available:

```powershell
Set-Location 'C:\Users\go\Documents\Codex\2026-10-16\task\tokyo-island'
& 'C:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe' -B .\hand_shapes_app.py
```

Options: `--count-stable-ms 180 --hold-seconds 0 --fade-seconds 3 --max-segments 1920`, `--width 960 --height 540`, optional `--fullscreen`. Q, Escape and window close exit through the shared lifecycle, which releases the detector, camera and scene window. No dependencies were installed.

## Verification

All **16 shape tests passed**, and the full related suite passed **92 tests in 2.076 seconds**. The shared suite command is in `HAND_DRAWING_DEVELOPMENT_20261019.md`. Synthetic tests check count stabilization, distinct shapes, rotated/letterboxed hand coverage, independent random styles across eight hands, changed detector order, transitions, single retirement on loss, re-entry, complete disappearance, and bounded history. A viewport-edge regression verifies retired outlines are clipped at their intersections rather than flattened into false border lines. A mocked shared-runner test covers camera loss and cleanup for this scene.

The actual controller and renderer generated these Library-uploaded previews outside Git in `..\artifacts\hand-shapes`:

- `hand_shapes_five_counts.png`: all five shapes fully visible for comparison.
- `hand_shapes_eight_hands.png`: eight hands with eight unique styles.
- `hand_shapes_synthetic_demo.gif`: nine-second synthetic sequence with movement, size/angle changes, count changes, fists and complete disappearance.
- `hand_shapes_before_during_after.png`: active, fading and empty states.

The demo used at most eight live shapes, 327 of 1920 history segments and 182 retired edges in one update; final history was zero. All previews state synthetic hands/no camera and contain no captured camera imagery. The reproducible generator and evidence JSON are outside the repository under `..\tmp\render_hand_shapes_demo.py` and the artifact folder respectively.

## Remaining real-device checks

No real camera or live production monitor was used. Four people with eight simultaneously visible hands, physical overlap/re-identification, venue lighting, finger-count reliability, scale/coverage at real distances, visual comfort, physical monitor placement and total camera/inference/render performance still require hardware testing. Synthetic landmarks and generated previews do not establish those results. Existing running applications were not stopped.
