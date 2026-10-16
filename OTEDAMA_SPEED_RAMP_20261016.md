# Otedama play-time speed ramp (2026-10-16)

`modern_otedama.py` starts at the previous 1.0x physics speed. Active play time raises the physics time scale linearly to 1.5x over **90 seconds**, then holds it there. At 30 seconds the scale is 1.1667x and at 60 seconds it is 1.3333x. `SPEED_RAMP_SECONDS` and `MAX_SPEED_MULTIPLIER` are next to the existing physics constants. The 50% ceiling bounds difficulty for the children's hand game.

Only `STATE_PLAYING` with a usable camera frame advances the ramp. Title/game-over waiting, the first frame after starting/replaying or recovering the camera, and stopped intervals longer than 0.5 seconds are excluded. Replay and a new scene reset to 1.0x. The elapsed clock uses active real seconds independently of the 100 ms physics budget, including at 5 FPS. Long gaps are discarded rather than caught up. Thus an overloaded machine may simulate slower motion while the difficulty clock still measures active time.

Motion, gravity, and air resistance share the time scale; velocity is not multiplied repeatedly. Every physics substep checks hands, including after an earlier hit. A ball scores at most once per displayed frame as before. Zero-time steps do not move or collide. Camera loss clears stale hands and freezes play, and retains the existing one-second failure timeout. Button behavior, art, and NEXT/BACK ownership are unchanged.

## Verification

Synthetic tests cover intermediate speed, the 90-second cap, title/game-over/stall exclusion, replay reset, 5/10/30/60/120 FPS progression, 30/60 FPS motion, all-substep collision checks, zero-time behavior, camera loss and recovery, shared-camera startup acknowledgement, Escape cleanup, and the single playlist registration. All 10 Otedama tests passed. No physical camera, audience display, or child play test was performed. The required audience display (`\\.\DISPLAY5`) was absent from the earlier production preflight.
