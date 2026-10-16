# Production hand/input feedback (2026-10-16)

## Scope and implementation

All 19 entries in `configs/rebirth_operator_acer_xiaomi.json` now show detected hand bones and a palm-center circle (Earth was added after the initial 18-scene pass; see `EARTH_PRODUCTION_ADOPTION_20261016.md`). Muted gray bones/circles identify detection; a steady cyan/white marker with a dark border identifies the part actually used by that scene. There is no default active finger. Existing backgrounds, artwork, logo transitions, camera ownership, operator controls and NEXT/BACK remain in their existing paths.

`hand_focus_overlay.py` renders Pygame and OpenCV feedback from Solutions landmarks, Tasks landmarks or immutable worker snapshots. It uses the scene's existing mirrored inference frame and its exact letterbox transform. There is no additional mirror. Filtered inputs can supply explicit active points. Otedama supplies its exact palm collision centers/radii. `hand_focus_pygfx.py` places the same RGBA drawing in a final orthographic render pass so 3D particles do not cover it; the old duplicated sphere cursors are replaced and their state colors remain in the marker centers.

The 14 scenes that already infer hands reuse their existing results. Five scenes without a hand model use one lightweight `PassiveHandDetector` at up to 15 Hz on the existing acquired frame. It owns no camera and closes with the scene. Missing frames and empty results clear feedback; cached passive results last at most one sampling interval. The Spheres worker copies landmarks before publishing its immutable snapshot. Skeleton, Earth and Otedama also clear feedback after 0.25 seconds of repeated shared-memory frame IDs. Otedama freezes gameplay during this camera stall and excludes the first recovery interval.

## Scene mapping

| Production entrypoint | Implementation | Bright input indicator |
| --- | --- | --- |
| `fractal_moving_acer.py` | `fractal_moving_2.py` | Index fingertip (8) |
| `finger_mandala_acer.py` | `finger_mandala_3.py` | Accepted participant index drawing points, after tracking/deduplication |
| `colorfull_wave_dots_acer.py` | `colorfull_wave_dots.py` | All five fingertips; all repel particles |
| `colorfull_tree_acer.py` | `colorfull_tree.py` | Wrist and raised fingertips; two-hand mode also uses middle MCP, thumb/index opening |
| `sci_fi_jacket_acer.py` | `sci_fi_jacket.py` | No active finger; garment segmentation remains the input |
| `skeleton_glitch_acer.py` | `skeleton_glitch.py` | No active finger; existing full-body pose/glitch display remains |
| `particle_storm_acer.py` | `particle_storm_2.py` | Index position and palm/open-close gesture; red/cyan state centers retained |
| `colorfull_dots_spheres_acer.py` | `colorfull_dots_spheres.py` | Smoothed index points passed to the sphere field |
| `finger_colorfull_dots_acer.py` | `finger_colorfull_dots_2.py` | Index fingertip (8) |
| `spider_cursor_acer.py` | `spider_cursor_2.py` | Detected index fingertips; automatic offset spider is not a detected hand |
| `finger_grid_interaction_acer.py` | `finger_grid_interaction_2.py` | Index fingertip; thumb added while the cutting pinch is active |
| `saturn_particles_acer.py` | `saturn_particles_2.py` | Index position and thumb/index pinch; gold/cyan hand assignment centers retained |
| `prism_skin_acer.py` | `prism_skin.py` | Index fingertip (8) |
| `polygon_vibes_acer.py` | `polygon_vibes_stage.py` | Index fingertip (8) |
| `kaleidoscope_camera_acer.py` | `kaleidoscope_camera.py` | No active finger; hand drawing passes through the same polar remap as the camera |
| `polygon_face_acer.py` | `polygon_face_stage.py` | Mouth center (face landmarks 13/14); hands are passive |
| `living_mosaic_acer.py` | `living_mosaic.py` | No active finger; full-image motion remains the input |
| `modern_otedama_acer.py` | `modern_otedama.py` | Actual palm collision circle and its center |
| `earth_acer.py` | `earth.py` | Actual left/right palm centers in the existing camera HUD; no fingertip input |

## Verification

The complete suite was run with Python 3.12.10, pygame-ce 2.5.7, MediaPipe 0.10.14, OpenCV 4.12.0 and dummy SDL video/audio. Native libraries must be imported before discovery because older tests install global mock modules via `sys.modules.setdefault`. A plain discovery attempt was contaminated by these mocks; this is not a scene-runtime failure. Normal production launch does not import the test modules or install these mock objects. Existing AST timing tests were updated to provide the newly imported overlay dependency while retaining all timing assertions.

Reproducible suite command, with the production Python and a writable TEMP/TMP directory:

```powershell
$env:SDL_VIDEODRIVER='dummy'
$env:SDL_AUDIODRIVER='dummy'
python -c "import cv2,numpy,pygame; import unittest; r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests')); raise SystemExit(not r.wasSuccessful())"
```

Final suite: **632 tests run, 631 passed, 1 skipped, 0 failures/errors** (30.210 seconds). The skipped GLFW fullscreen test requires the opt-in `KIDZDISCO_TEST_GLFW=1` graphics/display check. Coverage includes shared-camera ownership/cleanup, startup protocol, NEXT/BACK/fixture process switching, Otedama's 90-second speed ramp, missing/frozen camera input, mirrored/letterbox coordinates, true input selection, draw order, hand loss and Pygfx transparency/depth behavior. The isolated final Otedama/common-overlay/manager-switch run passed all 25 tests. An earlier combined run had one transient Windows `WinError 5` in fixture switching; the isolated repeat and final complete run passed all five consecutive real fixture promotions and cleanup. `git diff --check` passed.

Representative synthetic images were generated with real scene renderers and visually inspected: Grid (index/pinch), Tree (one/two hands), Prism Skin, Polygon Vibes, Spheres, Kaleidoscope, Polygon Face, Skeleton, Living Mosaic, Particle Storm, Saturn, and Otedama. Pygfx callbacks rendered offscreen with the actual 40,000/45,000 particle systems. Bright and dark backgrounds, multiple hands and 4:3-to-16:9 letterboxing were covered. These are simulated-input checks, not camera recognition measurements. Images/logs are retained in the task's `artifacts/hand-feedback/` folder outside Git; no personal imagery or generated media was added to the repository.

## Hardware checks still required

The earlier production preflight found only `\\.\DISPLAY1`, not the configured audience `\\.\DISPLAY5`. Live recognition accuracy, end-to-end delay, the extra hand detector's load in the five passive scenes, real NEXT/BACK display transitions and camera release still need an on-site run. Connect the intended camera and audience screen, cycle all 18 scenes, check one/two hands and disappearance, test a 90-second Otedama game and restart, then exit from the operator panel. Do this when the production machine is free.

The original production checkout and its uncommitted exposure setting were not changed. Work was performed in the separate `matahariland` checkout, with the speed ramp and visual feedback in separate commits.
