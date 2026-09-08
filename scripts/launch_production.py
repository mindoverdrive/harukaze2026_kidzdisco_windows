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


def check():
    sys.path.insert(0, str(ROOT))
    from stage_display import configure_audience_dpi, resolve_audience_displays
    configure_audience_dpi()
    config = json.loads((ROOT / 'configs/rebirth_operator_acer_xiaomi.json').read_text())
    for module in ('numpy', 'cv2', 'pygame', 'mediapipe', 'pygfx', 'wgpu', 'screeninfo', 'glfw'):
        if importlib.util.find_spec(module) is None:
            raise RuntimeError('Missing dependency: ' + module)
    for scene in config['PRODUCTION_SCENES']:
        if not (ROOT / scene).is_file():
            raise RuntimeError('Missing scene: ' + scene)
    displays = resolve_audience_displays(config)
    print('Preflight OK: %s scenes; control=%s; audience=%s' % (
        len(config['PRODUCTION_SCENES']), displays['control']['name'], displays['audience']['name']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    check()
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
        with stdout.open('wb') as out, stderr.open('wb') as err:
            process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'scripts/start_operator.py')],
                                       cwd=ROOT, stdout=out, stderr=err,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
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
                state = status(URL_PATTERN.search(url).group(1))['scene']
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
