# Otedama: three participants, both hands (2026-10-16)

## Base and scope

Continued `matahariland` from `a748b3813804ec29008cc87693199770ecc91bc1` in the separate task checkout. The original production directory and its local changes were not touched.

`modern_otedama.py` now configures its existing MediaPipe Solutions Hands detector with `MAX_HANDS = 6`, allowing up to three participants to use both hands. Model complexity and confidence settings are unchanged. This is a six-hand input capacity, without person identification or face recognition.

## Input, feedback and collisions

- Every detected hand independently contributes its existing palm collider (mean of wrist 0 and middle-finger MCP 9, existing radius limits). All colliders participate in ball collisions and the start/replay button. All corresponding skeletons, palm circles and active centers are drawn.
- Left/Right labels are not keys. Multiple participants' Left or Right hands do not overwrite one another. The collider list is rebuilt from every fresh detection result, so lost hands leave no cached collider. Missing/stalled camera frames retain the existing clearing and recovery behavior.
- There is no hand velocity inferred from detection index, label or previous-frame position. Reordering or re-entering hands therefore cannot transfer a different hand's velocity. Overlapping colliders retain the existing sequential collision response and ball speed cap; no person tracking or new collision model was introduced.
- Active play still reaches the 1.5x limit at 90 seconds. The background remains `(5, 5, 10)` and camera pixels remain hidden. Shared camera ownership, scene startup/exit, Manager NEXT/BACK, normal ball spawning, score rules and other scenes are unchanged.

## Verification

- **51 tests passed**: new six-hand tests (8), existing Otedama production tests (12), common hand-overlay tests (4), scene navigation (10), scene switching (10), and operator navigation (7). This includes repeated real fixture-process switching, without camera access. The restricted Windows sandbox initially blocked the fixture's localhost connection with WinError 10013; the same suite passed outside the sandbox in 4.554 seconds.
- New synthetic-input tests cover 0 through 6 hands, all six real Pygame palm markers, each hand's independent bounce and start interaction, three repeated Left and three repeated Right labels, reordered nonoverlapping detections, disappearance and moved re-entry with no stale hits/markers, and overlapping hands retaining finite bounded velocity with one score update per ball/frame.
- The existing tests continue to verify the 90-second/1.5x speed ramp, dark background with camera pixels hidden, shared-camera loss/recovery, FIRST_FRAME ordering, Escape and resource release. `git diff --check` passed.

The installed MediaPipe 0.10.14 detector was initialized with six-hand capacity, processed a synthetic blank image, and closed successfully. This confirms runtime/model compatibility, not live six-hand recognition.

The actual game renderer was inspected with six synthetic hand detections on the dark background; all six palm markers and skeletons were visible. The verification image labels its input as simulated. Six balls were placed for that illustration only; normal gameplay's spawning rules were not changed. The image remains outside Git.

## Hardware checks remaining

Three people simultaneously using both hands have **not** been tested with a physical camera. On the event setup, verify recognition of all six visible hands, repeated Left/Right labels, crossing/overlap, entry/exit, frame rate and latency, each hand's ball/start interaction, real-monitor NEXT/BACK, and camera release on exit. Do not interrupt an active event session.

Otedama screen fitting remains deferred until immediately before final verification. Logical rendering remains 1280 x 720; no screen-size change is included here.
