"""Camera-only kaleidoscope; fixed-size polar remap, no landmark dependency."""
from contextlib import ExitStack
import time
import numpy as np
import cv2
import pygame
import display_utils
from scene_control import notify_first_frame


def kaleidoscope_maps(width, height, now, sectors=6):
    y, x = np.mgrid[:height, :width].astype(np.float32)
    x -= (width - 1) / 2
    y -= (height - 1) / 2
    radius = np.sqrt(x * x + y * y)
    angle = np.arctan2(y, x) + now * .025
    wedge = np.pi * 2 / sectors
    folded = np.abs((angle + wedge / 2) % wedge - wedge / 2)
    # Reflection at source edges avoids blank outer corners.
    scale = .80 + .08 * np.sin(now * .07)
    mx = (width - 1) / 2 + radius * scale * np.cos(folded + now * .018)
    my = (height - 1) / 2 + radius * scale * np.sin(folded + now * .018)
    return mx.astype(np.float32), my.astype(np.float32)


def main():
    with ExitStack() as resources:
        pygame.init()
        resources.callback(pygame.quit)
        screen, _ = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()
        cap = display_utils.open_camera()
        if cap is None:
            raise RuntimeError('Kaleidoscope: camera unavailable')
        resources.callback(cap.release)
        if not cap.isOpened():
            raise RuntimeError('Kaleidoscope: shared camera unavailable')
        clock = pygame.time.Clock()
        started = time.monotonic()
        render_width, render_height = 640, max(1, round(640 * height / width))
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False
            if not running:
                break
            ok, frame = cap.read()
            screen.fill((0, 0, 0))
            if ok and frame is not None:
                _, stage, _ = display_utils.prepare_camera_frame(frame, render_width, render_height)
                mx, my = kaleidoscope_maps(render_width, render_height, time.monotonic() - started)
                image = cv2.remap(stage, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                surface = pygame.image.frombuffer(rgb.tobytes(), (render_width, render_height), 'RGB')
                screen.blit(pygame.transform.smoothscale(surface, (width, height)), (0, 0))
            pygame.display.flip()
            notify_first_frame(cap, frame_processed=bool(ok and frame is not None))
            clock.tick(60)


if __name__ == '__main__':
    main()
