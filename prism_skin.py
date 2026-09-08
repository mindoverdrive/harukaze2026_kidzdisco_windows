"""Prism Skin: shared camera + existing stage mapping, independent scene."""
from contextlib import ExitStack
import time
import cv2
import mediapipe as mp
import pygame
import display_utils
from prism_skin_field import PrismSkin
from scene_control import notify_first_frame


def main():
    with ExitStack() as resources:
        pygame.init()
        resources.callback(pygame.quit)
        screen, _ = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()
        cap = display_utils.open_camera()
        if cap is None:
            raise RuntimeError('Prism Skin: camera unavailable')
        resources.callback(cap.release)
        if not cap.isOpened():
            raise RuntimeError('Prism Skin: shared camera could not attach')
        hands = resources.enter_context(mp.solutions.hands.Hands(
            max_num_hands=5, model_complexity=1,
            min_detection_confidence=.5, min_tracking_confidence=.5))
        field = PrismSkin(320, max(90, round(320 * height / width)))
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
            points = []
            screen.fill((0, 0, 0))
            if ok and frame is not None:
                camera, stage, layout = display_utils.prepare_camera_frame(frame, width, height)
                result = hands.process(cv2.cvtColor(camera, cv2.COLOR_BGR2RGB))
                for hand in result.multi_hand_landmarks or []:
                    tip = hand.landmark[8]
                    points.append(display_utils.normalized_to_stage(tip.x, tip.y, layout))
                camera_rgb = cv2.cvtColor(stage, cv2.COLOR_BGR2RGB)
                screen.blit(pygame.image.frombuffer(camera_rgb.tobytes(), (width, height), 'RGB'), (0, 0))
            field.update([(x / (width - 1), y / (height - 1)) for x, y in points], dt)
            pixels = field.render(now - started)
            membrane = pygame.surfarray.make_surface(pixels.swapaxes(0, 1))
            membrane = pygame.transform.smoothscale(membrane, (width, height))
            membrane.set_alpha(155)
            screen.blit(membrane, (0, 0))
            for x, y in points:
                pygame.draw.circle(screen, (175, 245, 255), (x, y), 13, 1)
                pygame.draw.circle(screen, (250, 255, 255), (x, y), 4)
            pygame.display.flip()
            notify_first_frame(cap, frame_processed=bool(ok and frame is not None))
            clock.tick(60)


if __name__ == '__main__':
    main()
