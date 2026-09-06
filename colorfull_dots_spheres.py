"""Eight dense, luminous spheres rotating continuously around oblique axes.

Run through colorfull_dots_spheres_acer.py and Manager's shared camera.
Camera inference runs separately so animation does not wait for a new frame.
"""
from contextlib import ExitStack
import json
import time

from scene_control import notify_exit_request, notify_first_frame
from spheres_camera import SpheresCameraFeed
from spheres_visuals import SphereRenderer, TipSmoother


def main():
    import pygame
    import display_utils

    with ExitStack() as resources:
        def register_close(close):
            def finish(_kind, primary, _traceback):
                try:
                    close()
                except BaseException as cleanup_error:
                    if primary is None:
                        raise
                    try:
                        BaseException.add_note(primary, f"Scene cleanup failed: {type(cleanup_error).__name__}: {cleanup_error}")
                    except BaseException:
                        pass
                return False
            resources.push(finish)

        register_close(pygame.quit)
        pygame.init()
        screen, _size = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()
        pygame.display.set_caption("Colorful Dots Spheres")
        feed = SpheresCameraFeed(width, height)
        register_close(feed.close)
        feed.start()
        renderer = SphereRenderer(screen)
        smoother = TipSmoother()
        clock = pygame.time.Clock()
        # perf_counter is monotonic too, with sub-ms resolution on this Python/Windows.
        started = previous = metrics_started = time.perf_counter()
        draw_count = camera_count = 0
        camera_surface = cached_snapshot = presented_snapshot = None
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    notify_exit_request("pygame_quit")
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                    notify_exit_request("key_escape" if event.key == pygame.K_ESCAPE else "key_q")
                    running = False
            if not running:
                break
            now = time.perf_counter()
            elapsed = now - started
            dt, previous = min(0.1, max(0.0, now - previous)), now
            snapshot = feed.latest()
            if snapshot is None:
                cached_snapshot = camera_surface = None
            elif snapshot is not cached_snapshot:
                camera_surface = pygame.image.frombuffer(snapshot.rgb_bytes, snapshot.size, "RGB")
                # RGB24 global-alpha blending is expensive on the Windows RGB32 display.
                # Convert once per camera update, then reuse the fast display-format surface.
                camera_surface = camera_surface.convert(screen)
                camera_surface.set_alpha(70)
                cached_snapshot = snapshot
            tips = smoother.update(snapshot.tips if snapshot is not None else (), dt)
            screen.fill((1, 2, 6))
            if camera_surface is not None:
                screen.blit(camera_surface, (0, 0))
            visible = renderer.draw(screen, elapsed, tips)
            pygame.display.flip()
            draw_count += 1
            if snapshot is not None and snapshot is not presented_snapshot:
                # A first-frame acknowledgement means a real processed camera frame
                # has been presented, not just the camera-independent animation.
                notify_first_frame(snapshot, frame_processed=True)
                presented_snapshot = snapshot
                camera_count += 1
            interval = now - metrics_started
            if interval >= 10.0:
                try:
                    print("[SpheresMetrics] " + json.dumps({
                        "render_fps": draw_count / interval,
                        "camera_update_fps": camera_count / interval,
                        "particles": renderer.field.particle_count,
                        "drawn_particles": visible,
                        "hands": len(tips),
                        "camera_age_s": None if snapshot is None else max(0.0, time.monotonic() - snapshot.timestamp),
                    }), flush=True)
                except (OSError, ValueError):
                    pass
                metrics_started, draw_count, camera_count = now, 0, 0
            clock.tick(60)


if __name__ == "__main__":
    main()
