"""Standalone production adapter; old Harukaze scene remains untouched."""
from contextlib import ExitStack
import time
import cv2
import mediapipe as mp
import pygame
import display_utils
from polygon_vibes_field import PolygonField
from scene_control import notify_first_frame


def main():
    with ExitStack() as resources:
        pygame.init()
        resources.callback(pygame.quit)
        screen, _ = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()
        cap = display_utils.open_camera()
        if cap is None:
            raise RuntimeError('Polygon Vibes: camera unavailable')
        resources.callback(cap.release)
        if not cap.isOpened():
            raise RuntimeError('Polygon Vibes: shared camera unavailable')
        hands = resources.enter_context(mp.solutions.hands.Hands(
            max_num_hands=5, model_complexity=1,
            min_detection_confidence=.5, min_tracking_confidence=.5))
        field = PolygonField(width, height)
        surface = pygame.Surface((width, height))
        surface.set_alpha(175)
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
                rgb = cv2.cvtColor(stage, cv2.COLOR_BGR2RGB)
                screen.blit(pygame.image.frombuffer(rgb.tobytes(), (width, height), 'RGB'), (0, 0))
            triangles, colors = field.step(points, dt, now - started)
            surface.fill((8, 12, 20))
            for tri, color in zip(triangles.tolist(), colors.tolist()):
                pygame.draw.polygon(surface, color, tri)
            screen.blit(surface, (0, 0))
            for x, y in points:
                pygame.draw.circle(screen, (170, 245, 255), (x, y), 13, 1)
                pygame.draw.circle(screen, (255, 255, 255), (x, y), 4)
            pygame.display.flip()
            notify_first_frame(cap, frame_processed=bool(ok and frame is not None))
            clock.tick(60)


if __name__ == '__main__':
    main()
