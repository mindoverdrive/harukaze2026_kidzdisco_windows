"""Double-click convenience wrapper; production entry point remains unchanged."""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
URL_PATTERN = re.compile(r'http://127\.0\.0\.1:8766/#token=([A-Za-z0-9_-]+)')


def status(token):
    request = urllib.request.Request('http://127.0.0.1:8766/api/status',
                                     headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.load(response)


def find_panel(paths):
    for path in paths:
        try:
            with path.open('rb') as stream:
                text = stream.read(32768).decode('utf-8', errors='replace')
            match = URL_PATTERN.search(text)
            if match and isinstance(status(match.group(1)).get('scene'), dict):
                return match.group(0)
        except (OSError, ValueError):
            continue
    return None


def check(external_test=False, audience_name=None):
    sys.path.insert(0, str(ROOT))
    from stage_display import configure_audience_dpi, resolve_audience_displays
    configure_audience_dpi()
    config = json.loads((ROOT / 'configs/rebirth_operator_acer_xiaomi.json').read_text(encoding='utf-8'))
    for module in ('numpy', 'cv2', 'pygame', 'mediapipe', 'pygfx', 'wgpu', 'screeninfo', 'glfw'):
        if importlib.util.find_spec(module) is None:
            raise RuntimeError('Missing dependency: ' + module)
    for scene in config['PRODUCTION_SCENES']:
        if not (ROOT / scene).is_file():
            raise RuntimeError('Missing scene: ' + scene)
    if external_test:
        from stage_display import external_test_config
        from shared_camera import enumerate_camera_devices
        config = external_test_config(config, audience_name)
        devices = enumerate_camera_devices()  # names only; does not open a camera
        hints = [str(h).casefold() for h in config['CAMERA_NAME_HINTS']]
        excludes = [str(h).casefold() for h in config['CAMERA_EXCLUDE_HINTS']]
        matches = [(i, name) for i, name in enumerate(devices)
                   if any(h in name.casefold() for h in hints)
                   and not any(h in name.casefold() for h in excludes)]
        if len(matches) != 1:
            raise RuntimeError('Expected exactly one C922/C922n camera; no camera opened: ' + repr(devices))
        # Resolve the name again when Manager opens it; do not freeze enumeration index.
        config.update(CAMERA_OPENCV_INDEX=None, CAMERA_NAME_HINTS=[matches[0][1]],
                      CAMERA_REQUIRE_NAME_MATCH=True, CAMERA_ALLOW_FALLBACK=False,
                      CAMERA_STRICT_BACKEND=True, CAMERA_BACKEND='dshow')
        config['SCENE_DIR'] = str(ROOT)
        print('External camera candidate: ' + matches[0][1] + '; strict DShow; no fallback')
    displays = resolve_audience_displays(config)
    print('Preflight OK: %s scenes; control=%s; audience=%s' % (
        len(config['PRODUCTION_SCENES']), displays['control']['name'], displays['audience']['name']))
    if external_test:
        print('Physical-pixel geometry: ' + json.dumps(displays, ensure_ascii=False))
    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--external-test', action='store_true')
    parser.add_argument('--panel-only', action='store_true', help='Reopen an authenticated existing panel without hardware preflight or a new process')
    parser.add_argument('--audience-display', help='Explicit Windows display name when multiple external screens are connected')
    args = parser.parse_args()
    if args.audience_display and not args.external_test:
        parser.error('--audience-display requires --external-test')
    if args.panel_only:
        if args.check_only:
            parser.error('--panel-only and --check-only are mutually exclusive')
        reports = ROOT/'test_reports'
        logs = sorted(reports.glob('*.stdout.log'), key=lambda p: p.stat().st_mtime, reverse=True)
        url = find_panel(logs)
        if not url:
            raise RuntimeError('No authenticated operator panel found. No process started; inspect the latest logs.')
        if not webbrowser.open(url):
            raise RuntimeError('Open the current operator URL from the local startup log. No process started.')
        print('Opened existing operator panel; no hardware opened or process started.')
        return
    config = check(True, args.audience_display) if args.external_test else check()
    if args.check_only:
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, 'Local\\Rebirth2026ProductionLauncher')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    exists = ctypes.get_last_error() == 183
    try:
        if exists:
            print('Startup already in progress. Please wait.')
            return
        reports = ROOT / 'test_reports'
        with socket.socket() as probe:
            probe.settimeout(2)
            occupied = probe.connect_ex(('127.0.0.1', 8766)) == 0
        if occupied:
            logs = sorted(reports.glob('*.stdout.log'), key=lambda p: p.stat().st_mtime, reverse=True)
            url = find_panel(logs)
            if not url:
                raise RuntimeError('Port 8766 is already in use. Existing process was left untouched; check its operator URL.')
            webbrowser.open(url)
            print('Opened existing operator panel; no second Manager started.')
            return
        reports.mkdir(exist_ok=True)
        stem = 'production_launcher_' + time.strftime('%Y%m%d_%H%M%S') + '_' + str(os.getpid())
        stdout = reports / (stem + '.stdout.log')
        stderr = reports / (stem + '.stderr.log')
        command = [sys.executable, '-u', str(ROOT / 'scripts/start_operator.py')]
        if args.external_test:
            config_path = reports / (stem + '.config.json')
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
            command.extend(['--config', str(config_path)])
        environment = None
        if args.external_test:
            from stage_display import AUDIENCE_DPI_ENV
            environment = {k: v for k, v in os.environ.items()
                           if not k.startswith(('KIDZDISCO_', 'HARUKAZE_', 'MATAHARI_FACE_', 'SDL_'))}
            environment.update(AUDIENCE_DPI_ENV)
            environment.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        with stdout.open('wb') as out, stderr.open('wb') as err:
            spawn_options = {'env': environment} if environment is not None else {}
            process = subprocess.Popen(command,
                                       cwd=ROOT, stdout=out, stderr=err,
                                       creationflags=subprocess.CREATE_NO_WINDOW, **spawn_options)
        print('Starting production. Log: ' + str(stdout))
        opened = False
        until = time.monotonic() + 90
        while time.monotonic() < until:
            if process.poll() is not None:
                raise RuntimeError('Production process exited. See ' + str(stderr) + ' and ' + str(stdout))
            url = find_panel([stdout])
            if url:
                if not opened:
                    webbrowser.open(url)
                    opened = True
                try:
                    state = status(URL_PATTERN.search(url).group(1))['scene']
                except (OSError, ValueError):
                    time.sleep(1)
                    continue
                if state.get('error'):
                    raise RuntimeError('Manager reports: ' + str(state['error']))
                if state.get('current') and not state.get('busy') and not state.get('covered'):
                    print('Production ready: ' + state['current'])
                    return
            time.sleep(1)
        raise RuntimeError('Startup not confirmed within 90 seconds. Process was left running; inspect the operator panel and logs before retrying.')
    finally:
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('STARTUP CHECK: ' + str(exc), file=sys.stderr)
        sys.exit(1)
