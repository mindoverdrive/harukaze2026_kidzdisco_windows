"""Manual, single-window logo preview. No Manager, scene children or saved settings.

Launch through the adjacent CMD (isolated Python, existing dependencies only).
--render produces a synthetic contact sheet without opening a camera or window.
"""
import argparse
from functools import lru_cache
import json
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = Path.home() / '.gemini/antigravity/scratch/harukaze2026_kidzdisco_windows/.venv/Lib/site-packages'
ORDER = (("asobi_tune", "あそびTUNE"), ("colony", "Colony"),
         ("tokyo_island", "TOKYO ISLAND"))


class FixedBrandChoice:
    brand = ORDER[0][0]

    def choices(self, population, weights=None, k=1):
        if self.brand not in population or k != 1:
            raise ValueError('Unsupported preview brand selection')
        return [self.brand]


class PreviewController:
    def __init__(self, now=0):
        from transition_overlay import Curtain
        self.index = 0
        self.selector = FixedBrandChoice()
        self.curtain = Curtain(cover_duration=1.2, reveal_duration=1.6)
        self.pending = None
        self.running = True
        self.curtain.command('COVER', 1, now)

    def _cover(self, index, now):
        self.index = index
        self.selector.brand = ORDER[index][0]
        self.curtain.command('COVER', self.curtain.cycle + 1, now)

    def action(self, name, now):
        if name == 'quit':
            self.running = False
            return True
        if not self.running or self.curtain.state not in ('covered', 'idle'):
            return False
        if name not in ('next', 'back', 'replay', 'camera'):
            return False
        target = self.index + (1 if name == 'next' else -1 if name == 'back' else 0)
        if not 0 <= target < len(ORDER):
            return False
        if self.curtain.state == 'idle':
            self._cover(target, now)
        else:
            self.pending = None if name == 'camera' else target
            self.curtain.command('REVEAL', self.curtain.cycle, now)
        return True

    def presented(self, ack, now):
        if ack == 'REVEALED' and self.pending is not None:
            target, self.pending = self.pending, None
            self._cover(target, now)


class SoftwareOpacity:
    value = 255

    def __call__(self, value):
        self.value = value

    def sync(self):
        pass


class Renderer:
    def __init__(self, pygame, size, controller, effect_rng=None):
        from transition_branding import AlternatingCurtainLogo
        from transition_particles import ParticleCurtain
        self.pg, self.controller = pygame, controller
        self.stage = pygame.Surface(size, depth=32)
        self.layer = pygame.Surface(size, depth=32)
        self.output = pygame.Surface(size, depth=32)
        self.opacity = SoftwareOpacity()
        self.logo = AlternatingCurtainLogo(size, rng=controller.selector)
        self.particles = ParticleCurtain(size, rng=effect_rng)
        self.check_assets()

    def check_assets(self):
        if (self.logo.asobi is None or self.logo.tokyo is None
                or not self.logo.colony.available or not self.particles.available):
            raise RuntimeError('Logo/transition unavailable. Preview stopped; no substitute logo shown.')

    def compose(self, background):
        from transition_overlay import TRANSPARENT_COLOR
        self.output.blit(background, (0, 0))
        # Never apply global alpha to stage: breakup snapshots that surface.
        self.layer.set_alpha(None)
        self.layer.set_colorkey(None)
        self.layer.blit(self.stage, (0, 0))
        self.layer.set_colorkey(TRANSPARENT_COLOR)
        self.layer.set_alpha(self.opacity.value)
        self.output.blit(self.layer, (0, 0))
        return self.output

    def draw(self, now, background, flip=None):
        from transition_overlay import present_frame
        self.check_assets()

        def present():
            self.check_assets()
            frame = self.compose(background)
            if flip is not None:
                flip(frame)

        facade = SimpleNamespace(display=SimpleNamespace(flip=present), draw=self.pg.draw)
        curtain = self.controller.curtain
        ack = present_frame(self.stage, facade, curtain, now,
                            opacity=self.opacity,
                            draw_background=lambda rect: self.particles.draw(self.stage, rect, now, curtain),
                            draw_logo=lambda rect: self.logo.draw(self.stage, rect, now, curtain),
                            draw_breakup=lambda: self.particles.breakup(self.stage, now, curtain))
        # REVEALED must actually be presented before the brand changes.
        self.controller.presented(ack, now)
        return self.output


class CameraSource:
    """One DirectShow capture owner, newest frame only; UI never waits on read()."""
    def __init__(self, index, capture_factory=None, clock=time.monotonic):
        self.index, self.capture_factory, self.clock = index, capture_factory, clock
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame, self._stamp = None, None
        self._status = 'Camera opening...'
        self._thread = threading.Thread(target=self._run, name='logo-preview-camera', daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        cap = None
        try:
            import cv2
            factory = self.capture_factory or cv2.VideoCapture
            cap = factory(self.index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                raise RuntimeError('Camera unavailable or already in use')
            # No exposure, gain, zoom or production camera settings are applied.
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise RuntimeError('Camera frame unavailable; restart preview to retry')
                with self._lock:
                    self._frame, self._stamp = frame.copy(), self.clock()
                    self._status = 'Camera live'
        except Exception as exc:
            with self._lock:
                self._frame, self._stamp = None, None
                self._status = str(exc)
        finally:
            if cap is not None:
                cap.release()

    def snapshot(self, now=None):
        with self._lock:
            now = self.clock() if now is None else now
            if self._stamp is not None and 0 <= now - self._stamp <= 1.0:
                return self._frame, self._status
            status = 'Camera signal stale' if self._stamp is not None else self._status
            return None, status

    def close(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=0.5)
        # A blocked native read is left to its daemon owner/process exit.
        # Never race cap.release() against read(), never open another capture.


def _table_has_production_listener(data):
    count, = struct.unpack_from('<I', data)
    if len(data) < 4 + count * 24:
        raise ValueError('Truncated Windows TCP table')
    return any(state == 2 and socket.ntohs(port & 0xffff) == 8766
               for state, address, port, remote, remote_port, pid
               in struct.iter_unpack('<6I', data[4:4 + count * 24]))


def _production_port_active():
    """Read the TCP table; do not connect, bind, send or stop any process."""
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('iphlpapi', use_last_error=True).GetExtendedTcpTable
    api.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                    wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    api.restype = wintypes.DWORD
    size = wintypes.DWORD()
    if api(None, ctypes.byref(size), False, 2, 3, 0) not in (0, 122):
        return True
    buffer = ctypes.create_string_buffer(size.value)
    if api(buffer, ctypes.byref(size), False, 2, 3, 0) != 0:
        return True
    return _table_has_production_listener(buffer.raw)


def production_camera_active():
    """Conservatively guard known Manager owners; read files/process state only."""
    import ctypes
    from ctypes import wintypes
    try:
        if _production_port_active():
            return True
    except (OSError, ValueError, struct.error):
        return True
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    for folder in (ROOT, PACKAGES.parents[2]):
        path = folder / '.shared_camera_session.json'
        if not path.exists():
            continue
        try:
            pid = json.loads(path.read_text(encoding='utf-8'))['pid']
            if type(pid) is not int or pid <= 0:
                return True
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                if ctypes.get_last_error() == 87:  # No such PID.
                    continue
                return True
            try:
                code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259:
                    return True
            finally:
                kernel.CloseHandle(handle)
        except (ValueError, KeyError, TypeError, OSError):
            return True
    return False


def enumerate_cameras():
    # Enumerate names only. No filter is bound and no camera is opened here.
    from pygrabber.dshow_graph import SystemDeviceEnum
    from pygrabber.dshow_ids import DeviceCategories
    return list(SystemDeviceEnum().get_available_filters(DeviceCategories.VideoInputDevice))


def checker(pygame, size):
    surface = pygame.Surface(size)
    for y in range(0, size[1], 32):
        for x in range(0, size[0], 32):
            color = (37, 45, 58) if (x // 32 + y // 32) % 2 else (53, 64, 78)
            pygame.draw.rect(surface, color, (x, y, 32, 32))
    return surface


def fit_camera(pygame, frame, size):
    # Preserve camera aspect; mirror for a natural self-view. No frame is saved.
    source = pygame.surfarray.make_surface(frame[:, ::-1, ::-1].swapaxes(0, 1))
    scale = min(size[0] / source.get_width(), size[1] / source.get_height())
    scaled = pygame.transform.smoothscale(source, (max(1, round(source.get_width() * scale)),
                                                   max(1, round(source.get_height() * scale))))
    result = pygame.Surface(size)
    result.fill((12, 16, 24))
    result.blit(scaled, scaled.get_rect(center=result.get_rect().center))
    return result


def preview_geometry(work_area):
    left, top, right, bottom = work_area
    width = min(1120, right - left - 48, int((bottom - top - 180) * 16 / 9))
    if width < 480:
        raise RuntimeError('Screen work area too small for the preview controls')
    height = round(width * 9 / 16)
    return (width, height), (left + (right - left - width) // 2,
                             top + max(0, (bottom - top - height - 140) // 2))


@lru_cache(maxsize=16)
def ui_font(pygame, size):
    return pygame.font.SysFont('yugothicui,meiryo,msgothic,segoeui', size)


def select_camera(pygame, window, font, clock):
    try:
        names = enumerate_cameras()
        error = '' if names else 'No cameras found. Connect a camera and restart to retry.'
    except Exception:
        names, error = [], 'Camera list unavailable. Synthetic preview is available.'
    choices = [(i, f'{i}: {name}') for i, name in enumerate(names)] + [(None, 'カメラなし / Synthetic background')]
    selected = 0
    rows = []
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q)):
                return False, None, ''
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(choices)
                if event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(choices)
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return True, choices[selected][0], choices[selected][1]
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, rect in rows:
                    if rect.collidepoint(event.pos):
                        return True, choices[i][0], choices[i][1]
        window.fill((14, 20, 31))
        window.blit(font.render('試用するカメラを選択 / Choose camera', True, (235, 242, 250)), (24, 24))
        window.blit(font.render('↑ ↓ / Enter  または項目をクリック', True, (153, 187, 215)), (24, 60))
        rows = []
        visible_count = max(1, (window.get_height() - 180) // 48)
        first = max(0, selected - visible_count + 1)
        for i in range(first, min(len(choices), first + visible_count)):
            rect = pygame.Rect(20, 112 + (i - first) * 48, window.get_width() - 40, 42)
            rows.append((i, rect))
            pygame.draw.rect(window, (38, 82, 105) if i == selected else (28, 38, 53), rect, border_radius=6)
            window.blit(font.render(choices[i][1], True, (235, 242, 250)), (rect.x + 12, rect.y + 6))
        if error:
            window.blit(ui_font(pygame, 16).render(error, True, (255, 204, 141)), (24, window.get_height() - 36))
        pygame.display.flip()
        clock.tick(30)


BUTTONS = (('back', 'BACK [←]'), ('next', 'NEXT [→]'), ('replay', 'REPLAY [Space]'),
           ('camera', 'CAMERA [C]'), ('quit', 'EXIT [Esc]'))


def draw_ui(pygame, window, stage_height, controller, status):
    width = window.get_width()
    pygame.draw.rect(window, (14, 20, 31), (0, stage_height, width, window.get_height() - stage_height))
    state = controller.curtain.state
    state_text = '切替中' if state in ('covering', 'revealing') else '操作待ち'
    label = f'{controller.index + 1} / 3   {ORDER[controller.index][1]}    {state_text}'
    window.blit(ui_font(pygame, 22).render(label, True, (235, 242, 250)), (16, stage_height + 8))
    rects = {}
    button_width = (width - 32 - 8 * 4) // 5
    for i, (action, text) in enumerate(BUTTONS):
        rect = pygame.Rect(16 + i * (button_width + 8), stage_height + 40, button_width, 38)
        rects[action] = rect
        enabled = (action == 'quit' or (state in ('covered', 'idle')
                   and not (action == 'back' and controller.index == 0)
                   and not (action == 'next' and controller.index == 2)))
        pygame.draw.rect(window, (37, 88, 111) if enabled else (29, 39, 51), rect, border_radius=5)
        rendered = ui_font(pygame, max(12, min(18, button_width // 9))).render(text, True,
                         (239, 247, 252) if enabled else (109, 128, 145))
        window.blit(rendered, rendered.get_rect(center=rect.center))
    window.blit(ui_font(pygame, 15).render(status, True, (174, 193, 212)), (16, stage_height + 87))
    return rects


def run_live(pygame):
    import ctypes
    from ctypes import wintypes
    # Process-local DPI setting; no system setting is changed.
    ctypes.windll.user32.SetProcessDPIAware()
    work = wintypes.RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(work), 0):
        raise RuntimeError('Cannot determine primary screen work area')
    size, position = preview_geometry((work.left, work.top, work.right, work.bottom))
    os.environ['SDL_VIDEO_WINDOW_POS'] = f'{position[0]},{position[1]}'
    pygame.display.init()
    window = pygame.display.set_mode((size[0], size[1] + 112))
    pygame.display.set_caption('TOKYO ISLAND 2026 — Logo / Windows camera preview')
    clock = pygame.time.Clock()
    active, index, camera_name = select_camera(pygame, window, ui_font(pygame, 24), clock)
    if not active:
        return
    source = None
    status = 'Synthetic background / C: カメラ背景を見る、Space: ロゴ再生'
    try:
        controller = PreviewController()
        renderer = Renderer(pygame, size, controller)
        synthetic = checker(pygame, size)
        if index is not None:
            if production_camera_active():
                status = 'Production camera owner active. Camera not opened; synthetic background.'
            else:
                # Revalidate the chosen name immediately before opening; never guess an index.
                try:
                    names = enumerate_cameras()
                except Exception:
                    names = []
                if index >= len(names) or f'{index}: {names[index]}' != camera_name:
                    status = 'Camera list changed. Camera not opened; restart preview to select again.'
                else:
                    source = CameraSource(index)
                    source.start()
        keys = {pygame.K_RIGHT: 'next', pygame.K_n: 'next', pygame.K_RETURN: 'next',
                pygame.K_LEFT: 'back', pygame.K_b: 'back', pygame.K_SPACE: 'replay',
                pygame.K_r: 'replay', pygame.K_c: 'camera', pygame.K_ESCAPE: 'quit', pygame.K_q: 'quit'}
        buttons = {}
        animation_started = time.monotonic()
        while controller.running:
            now = time.monotonic() - animation_started
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    controller.action('quit', now)
                elif event.type == pygame.KEYDOWN and not getattr(event, 'repeat', False):
                    controller.action(keys.get(event.key), now)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for action, rect in buttons.items():
                        if rect.collidepoint(event.pos):
                            controller.action(action, now)
            if not controller.running:
                break
            background = synthetic
            if source is not None:
                frame, message = source.snapshot()
                status = f'{camera_name} | {message}'
                if frame is not None:
                    background = fit_camera(pygame, frame, size)
                else:
                    status += ' | Synthetic background'

            def flip(frame):
                nonlocal buttons
                window.blit(frame, (0, 0))
                buttons = draw_ui(pygame, window, size[1], controller, status)
                pygame.display.flip()

            renderer.draw(now, background, flip)
            clock.tick(60)
    finally:
        if source is not None:
            source.close()


def render_contact_sheet(pygame, path):
    size = (640, 360)
    controller = PreviewController()
    renderer = Renderer(pygame, size, controller)
    background = checker(pygame, size)
    sheet = pygame.Surface((size[0] * 3, 880))
    sheet.fill((14, 20, 31))
    font = ui_font(pygame, 28)
    sheet.blit(font.render('TOKYO ISLAND 2026 / Manual logo preview', True, (235, 242, 250)), (20, 12))
    sheet.blit(ui_font(pygame, 19).render('Synthetic background. No camera captured. Top: hold / Bottom: release + persistent controls.', True, (174, 193, 212)), (20, 51))
    now = 0.0
    for index in range(3):
        now += 1.3
        renderer.draw(now, background)
        window = pygame.Surface((640, 472))
        window.blit(renderer.output, (0, 0))
        draw_ui(pygame, window, 360, controller, 'Synthetic preview / C: show camera / Space: logo')
        # Full-size logo plus UI at the top; breakup detail below.
        sheet.blit(window, (index * 640, 90))
        controller.action('next' if index < 2 else 'replay', now)
        renderer.draw(now + .50, background)
        sheet.blit(pygame.transform.smoothscale(renderer.output, (560, 315)), (index * 640 + 40, 565))
        renderer.draw(now + 1.7, background)
        now += 1.7
    pygame.image.save(sheet, str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', type=Path, help='Save synthetic contact sheet; no device/window access')
    args = parser.parse_args(argv)
    # Do not run sitecustomize or .pth files; use only this repo and existing deps.
    sys.path[:0] = [str(ROOT), str(PACKAGES)]
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    if args.render:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    import pygame
    pygame.font.init()
    try:
        if args.render:
            render_contact_sheet(pygame, args.render)
        else:
            run_live(pygame)
    finally:
        ui_font.cache_clear()
        pygame.quit()


if __name__ == '__main__':
    main()
