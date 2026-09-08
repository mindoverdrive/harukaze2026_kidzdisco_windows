"""One-face production adapter: mouth opening drives polygon waves."""
from contextlib import ExitStack
import time
import cv2
import mediapipe as mp
import pygame
import display_utils
from polygon_face_field import FaceField, mouth_openness
from scene_control import notify_first_frame


def main():
    with ExitStack() as resources:
        pygame.init()
        resources.callback(pygame.quit)
        screen, _ = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()
        cap = display_utils.open_camera()
        if cap is None:
            raise RuntimeError('Face Polygon: camera unavailable')
        resources.callback(cap.release)
        if not cap.isOpened():
            raise RuntimeError('Face Polygon: shared camera unavailable')
        detector = resources.enter_context(mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=False,
            min_detection_confidence=.5, min_tracking_confidence=.5))
        field = FaceField(width, height)
        surface = pygame.Surface((width, height))
        surface.set_alpha(155)
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
            mouth, opening = None, 0.
            screen.fill((0, 0, 0))
            if ok and frame is not None:
                camera, stage, layout = display_utils.prepare_camera_frame(frame, width, height)
                result = detector.process(cv2.cvtColor(camera, cv2.COLOR_BGR2RGB))
                if result.multi_face_landmarks:
                    lm = result.multi_face_landmarks[0].landmark
                    opening = mouth_openness(lm)
                    mouth = display_utils.normalized_to_stage((lm[13].x + lm[14].x) / 2,
                                                               (lm[13].y + lm[14].y) / 2, layout)
                rgb = cv2.cvtColor(stage, cv2.COLOR_BGR2RGB)
                screen.blit(pygame.image.frombuffer(rgb.tobytes(), (width, height), 'RGB'), (0, 0))
            triangles, colors = field.step(mouth, opening, dt, now - started)
            surface.fill((8, 12, 20))
            for tri, color in zip(triangles.tolist(), colors.tolist()):
                pygame.draw.polygon(surface, color, tri)
            screen.blit(surface, (0, 0))
            if mouth is not None:
                pygame.draw.circle(screen, (255, 245, 190), mouth, round(8 + field.opening * 16), 2)
            pygame.display.flip()
            notify_first_frame(cap, frame_processed=bool(ok and frame is not None))
            clock.tick(60)


if __name__ == '__main__':
    main()
