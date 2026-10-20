"""Opt-in verification HUD and numeric telemetry. Never saves camera pixels."""
import json
import os
import time
from collections import deque
from face_morph_field import FORMS


class FaceCheckDiagnostics:
    def __init__(self, pygame):
        self.pg = pygame
        self.font = pygame.font.SysFont('Yu Gothic UI,Meiryo', 16)
        self.presentations = deque(maxlen=180)
        self.detections = deque(maxlen=180)
        self.last_log = 0.
        self.detect_ms = 0.
        self.draw_ms = 0.
        self.phase = ''
        self.label = os.environ.get('MATAHARI_FACE_CHECK_DISPLAY', '確認用表示・本番未受入')
        print('[face_check_renderer] '+json.dumps({'sdl_driver':pygame.display.get_driver(),
              'surface_size':pygame.display.get_surface().get_size(),
              'window_size':pygame.display.get_window_size(),
              'surface_flags':pygame.display.get_surface().get_flags(),
              'mesh_renderer':'OpenCV CPU; pygame SDL presentation',
              'gpu_mesh_execution_verified':False}),flush=True)

    @staticmethod
    def rate(samples, now):
        recent = [stamp for stamp in samples if now - stamp <= 2.]
        span=recent[-1]-recent[0] if len(recent)>1 else 0.
        return round((len(recent)-1)/span,1) if span>0 else 0.

    def detected(self, now, duration=0., phase=''):
        self.detections.append(now)
        self.detect_ms=duration*1000
        self.phase=phase

    def snapshot(self, field, now):
        return {'event': 'face_mesh_measurement', 'monotonic': now,
                'recognized': getattr(field, 'last_observation_count', 0),
                'visible': sum(t.visible for t in field.tracks.values()),
                'reserved_tracks': len(field.tracks),
                'ambiguous': getattr(field, 'last_ambiguous_count', 0),
                'changes': field.changes,
                'render_fps': self.rate(self.presentations, now),
                'detection_hz': self.rate(self.detections, now),
                'detect_ms': round(self.detect_ms, 3), 'draw_ms': round(self.draw_ms, 3), 'phase': self.phase,
                'tracks': [{'id': key, 'visible': t.visible, 'uncertain': t.uncertain,
                            'mouth': 'open' if t.opened else 'closed', 'opening': round(t.opening, 3),
                            'armed': t.armed, 'pending_open': t.pending_open,
                            'changes': getattr(t, 'changes', None),
                            'shape': FORMS[t.shape],
                            'previous_shape': FORMS[t.previous_shape] if t.previous_shape is not None else None}
                           for key, t in field.tracks.items()]}

    def draw(self, screen, field, now):
        data = self.snapshot(field, now)
        lines = [f"口mesh確認 | {self.label} | ESCで終了",
                 f"認識 {data['recognized']} / 表示 {data['visible']} / 予約ID {data['reserved_tracks']} / 曖昧 {data['ambiguous']}   描画 {data['render_fps']} FPS / 検出 {data['detection_hz']} Hz",
                 f"{self.phase} | 検出／入力 {self.detect_ms:.1f}ms / メッシュ描画 {self.draw_ms:.1f}ms | 閉じる→1回開くと変身→閉じて次へ"]
        for t in data['tracks']:
            state = '曖昧・抑止' if t['uncertain'] else ('可視' if t['visible'] else '見失い')
            trigger='変形完了待ち' if t['pending_open'] else '次の開口を受付' if t['armed'] else '閉口待ち'
            lines.append(f"ID {t['id']} {state}  口 {t['mouth']} {t['opening']:.2f}  {trigger}  変身 {t['changes']}  {t['previous_shape'] or ''} → {t['shape']}")
        width, height = screen.get_size()
        line_h = self.font.get_linesize()
        panel_h = min(height, line_h * len(lines) + 12)
        self.pg.draw.rect(screen, (12, 17, 25), (0, height-panel_h, width, panel_h))
        for index, line in enumerate(lines):
            screen.blit(self.font.render(line, True, (238, 243, 247)), (8, height-panel_h+6+index*line_h))

    def presented(self, field, now=None):
        now = time.monotonic() if now is None else now
        self.presentations.append(now)
        if now - self.last_log >= 1.:
            print('[face_check] ' + json.dumps(self.snapshot(field, now), ensure_ascii=False), flush=True)
            self.last_log = now
