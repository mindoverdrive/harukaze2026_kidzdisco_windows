# Earth production adoption (2026-10-16)

## Base, identity and assets

- Continued `matahariland` from `b0ce8be83051f079654b9f3ee92f1e253ee8b10e` in the separate task checkout. The original production folder and its uncommitted exposure setting were not edited.
- The requested scene is the existing `earth.py` / `EarthViewer3D`. It was absent from the explicit playlist. Added `earth_acer.py` using `run_scene("earth.py", profile="acer")`, once at the end: 19 scenes total.
- Existing tracked assets are reused unchanged: `real_earth_texture.jpg` (2048x1024, 593729 bytes), `galaxy_texture.jpg` (19828x5796, 20376421 bytes), `models/hand_landmarker.task` (7819105 bytes). `earth_texture.png` is not used.

## Appearance and controls

The Earth sphere, galaxy background, lights, idle rotation, control equations and top-right camera HUD are retained. The left palm center (mean of landmarks 0 and 9) rotates Earth; its 0-to-9 span controls zoom. The right palm center rotates the galaxy. **Fingertips are not inputs.** Common muted bones/palm circles and bright active palm centers are drawn in the existing HUD. Unknown handedness is passive; duplicate labels highlight only the last hand actually supplying that label's control values.

The HUD uses the same mirrored frame as inference and aspect-fit letterboxing, replacing the old stretch to 320x240. The 3D camera uses the current output aspect ratio. No second capture or detector was added. Galaxy JPEG decoding uses `draft`/thumbnail before RGBA conversion, retaining the 4096-wide texture budget while avoiding the former full-resolution ~460 MB RGBA allocation. Pillow's global image limit stays unchanged. Missing/unreadable assets produce an explicit startup error instead of an untextured fallback.

## Runtime contract

- Attach to the shared camera once; no camera-index retry or capture-size/FPS reconfiguration.
- Report FIRST_FRAME only after valid camera processing and both main/HUD render passes.
- Keep NEXT/BACK in the standard manager/profile wrapper, with no scene-local navigation detector.
- Failed/empty reads clear HUD/inputs and schedule a retry; repeated shared frame IDs expire after 0.25 s. A one-second failure stops the scene. Valid recovery restores inference.
- VIDEO timestamps use monotonic time with a strict increasing guard.
- Escape/q/window close notify the lifecycle and stop the loop. Constructor/run failures close every acquired capture/model/canvas through `ExitStack`; cleanup is idempotent. Callback exceptions are saved and re-raised after the loop returns because RenderCanvas internally logs/swallow callbacks; the runner therefore observes failure.

## Verification

New tests use synthetic frames and private AST namespaces without replacing global modules. The full-suite command follows `HAND_INPUT_FEEDBACK_20261016.md`: preload native cv2/numpy/pygame because older unrelated tests install global dummy modules. Normal production launch does not import those tests.

The real GPU renderer was exercised offscreen with the original textures. The tracked MediaPipe model initialized and processed a synthetic blank image; subsequent drawing used synthetic left/right landmarks. Both active palm centers appeared in the HUD; both render passes completed; camera loss cleared the HUD; capture/model cleanup completed. Texture sizes were 2048x1024 (Earth) and 4096x1197 (galaxy). `earth_synthetic.png` is simulated input, not a live camera image, and remains outside Git in the task artifacts folder.

- New Earth tests: **27 passed** (including fresh-resource restart and propagation of swallowed callback failures).
- Complete suite: **659 run, 658 passed, 1 skipped, 0 failures/errors** in 31.405 seconds. The skipped opt-in GLFW fullscreen test needs the physical graphics/display setup.
- `git diff --check` passed. Actual model/GPU checks used Python 3.12.10 from the verified Windows production runtime, without a physical camera or visible test window.
- `scripts/launch_production.py --check-only` stopped as designed: expected `\\.\DISPLAY5`, detected only `\\.\DISPLAY1`. It did not launch Manager or acquire a camera.

## Camera-HUD display request confirmed (2026-10-16)

The follow-up request to show hand detection inside Earth's camera view is already implemented by the adoption commit `96db86536142ef2465f8159be3163ff208fdab0b`. No duplicate overlay or Earth source change was needed. The separate Otedama camera-background removal does not affect Earth.

- Re-ran 27 Earth tests and 4 common-overlay tests: **31 passed**.
- Checked actual OpenCV overlay pixels in synthetic 640x360, 640x480, and 360x640 camera inputs. Each input is mirrored once before inference. Camera imagery and both active palm markers remain together in the 320x240 HUD, with image sizes/offsets of 320x180/(0,30), 320x240/(0,0), and 135x240/(92,0), respectively. Skeleton and palm projection use that same layout; there is no second mirror. Independent review also verified that unknown handedness remains passive.
- This verification used synthetic camera frames and hand landmarks; it did not acquire a physical camera or open a visible window.

## Hardware checks remaining

This is not production acceptance. The audience `\\.\DISPLAY5` was absent from this preflight. Live handedness/recognition, control feel, actual screen appearance, NEXT/BACK transitions, and repeated camera release/restart on the event setup remain to be checked when the machine is free. Otedama screen fitting remains separately recorded for immediately before final verification and is not implemented by this change.
