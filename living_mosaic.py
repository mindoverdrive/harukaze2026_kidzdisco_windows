"""Full camera mosaic: moving regions become six times coarser."""
from contextlib import ExitStack
import time
import cv2
import pygame
import display_utils
from living_mosaic_field import LivingMosaic
from scene_control import notify_first_frame


def main():
    with ExitStack() as resources:
        pygame.init()
        resources.callback(pygame.quit)
        screen, _ = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()
        cap = display_utils.open_camera()
        if cap is None:
            raise RuntimeError('Living Mosaic: camera unavailable')
        resources.callback(cap.release)
        if not cap.isOpened():
            raise RuntimeError('Living Mosaic: shared camera unavailable')
        rw, rh = 640, round(640 * height / width)
        mosaic = LivingMosaic(rw, rh)
        clock = pygame.time.Clock()
        started = previous = time.monotonic()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False
            if not running:
                break
            now = time.monotonic()
            dt, previous = now - previous, now
            ok, frame = cap.read()
            screen.fill((0, 0, 0))
            if ok and frame is not None:
                camera, _, _ = display_utils.prepare_camera_frame(frame, rw, rh)
                # Motion and face averages use undimmed input, not inverted output.
                source = display_utils.fit_frame_to_size(camera, rw, rh)
                output = mosaic.render(source, now-started, dt)
                # Opacity is applied AFTER inversion so zero still means black.
                output = display_utils.apply_camera_opacity(output, display_utils._camera_presentation.opacity())
                rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
                surface = pygame.image.frombuffer(rgb.tobytes(), (rw,rh), 'RGB')
                screen.blit(pygame.transform.smoothscale(surface, (width,height)), (0,0))
            pygame.display.flip()
            notify_first_frame(cap, frame_processed=bool(ok and frame is not None))
            clock.tick(30)


if __name__ == '__main__':
    main()
