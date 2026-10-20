"""Launch the existing Manager with a private three-scene Acer play profile."""
from pathlib import Path
import argparse
import datetime
import json
import os
import socket
import subprocess
import sys
import re
import time
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path(__file__).resolve().parents[1]
PORT = 8767
sys.path.insert(0, str(ROOT))


def open_panel_when_ready(process, stdout, timeout=30.0):
    """Open only this launch's authenticated loopback URL, on user invocation."""
    deadline = time.monotonic() + timeout
    pattern = re.compile(r'\[Operator\] (http://127\.0\.0\.1:8767/#token=[A-Za-z0-9_-]+)')
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Manager exited during startup. Check logs: ' + str(stdout.parent))
        match = pattern.search(stdout.read_text(encoding='utf-8', errors='replace'))
        if match:
            url = match.group(1)
            if not webbrowser.open(url):
                raise RuntimeError('Open this operator URL manually: ' + url +
                                   ' (Manager remains running; do not start a second copy.)')
            return
        time.sleep(.2)
    raise RuntimeError('Operator URL was not confirmed. Manager may remain running; check logs before retrying: ' + str(stdout.parent))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', choices=('shapes', 'drawing'), default='shapes')
    parser.add_argument('--open-panel', action='store_true', help='Open the operator page after this user-initiated launch')
    args = parser.parse_args()
    from tools.matahari_face_mesh_check import camera_activity, clean_env, code_version
    from shared_camera import enumerate_camera_devices
    from stage_display import AUDIENCE_DPI_ENV, configure_audience_dpi
    configure_audience_dpi()
    from screeninfo import get_monitors
    with socket.socket() as probe:
        probe.settimeout(.5)
        if probe.connect_ex(('127.0.0.1', PORT)) == 0:
            raise RuntimeError('Hand play port is occupied; existing session was left untouched.')
    activity = camera_activity()
    if activity['apps']:
        raise RuntimeError('Camera reported in use: ' + ', '.join(activity['apps']))
    cameras = enumerate_camera_devices()
    matches = [(i, name) for i, name in enumerate(cameras) if name == 'ACER HD User Facing']
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one ACER HD User Facing camera: ' + repr(cameras))
    index, name = matches[0]
    monitors = get_monitors()
    primary = next((m for m in monitors if m.is_primary), monitors[0])
    directory = PROJECT / 'test_reports/hand-play' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    directory.mkdir(parents=True, exist_ok=False)
    scenes = ['hand_shapes_acer.py', 'hand_drawing_acer.py']
    if args.scene == 'drawing':
        scenes.reverse()
    scenes.append('modern_otedama_acer.py')
    config = {
        'SCENE_DIR': str(ROOT),
        'PRODUCTION_SCENES': scenes,
        'PRELOAD_COUNT': 0, 'TRANSITION_ENABLED': True, 'CLAP_MONITOR_ENABLED': False,
        'SHARED_CAMERA_ENABLED': True, 'DISPLAY_TARGET': 'stage',
        'DISPLAY_X': primary.x, 'DISPLAY_Y': primary.y,
        'DISPLAY_WIDTH': primary.width, 'DISPLAY_HEIGHT': primary.height,
        'CAMERA_INDEX': index, 'CAMERA_OPENCV_INDEX': index,
        'CAMERA_NAME_HINTS': [name], 'CAMERA_EXCLUDE_HINTS': ['virtual', 'nizima'],
        'CAMERA_REQUIRE_NAME_MATCH': True, 'CAMERA_WIDTH': 1280, 'CAMERA_HEIGHT': 720,
        'CAMERA_FPS': 30, 'CAMERA_FOURCC': 'MJPG', 'CAMERA_EXPOSURE': None,
        'CAMERA_ZOOM': None, 'CAMERA_BACKEND': 'dshow', 'CAMERA_STRICT_BACKEND': True,
        'CAMERA_ALLOW_FALLBACK': False, 'CAMERA_DIAGNOSTIC_SECONDS': .5,
    }
    def save(filename, value):
        (directory / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    save('config.json', config)
    save('code-version.json', code_version())
    save('preflight.json', {'at': datetime.datetime.now().astimezone().isoformat(),
                           'python': sys.executable, 'cameras': cameras, 'camera_activity': activity,
                           'monitor': vars(primary), 'images_saved': False})
    bootstrap = (
        'import sys; from stage_display import configure_audience_dpi; configure_audience_dpi(); '
        'import shared_camera; shared_camera.SESSION_INFO_PATH = ' + repr(str(directory/'shared-camera.json')) + '; '
        'import manager; from scripts.start_operator import operator_session;\n'
        'with operator_session():\n    sys.exit(manager.main())'
    )
    command = [sys.executable, '-B', '-u', '-c', bootstrap,
               '--config', str(directory/'config.json'), '--report-dir', str(directory/'runtime'),
               '--operator-host', '127.0.0.1', '--operator-port', str(PORT)]
    env = clean_env()
    env.update(AUDIENCE_DPI_ENV)
    with (directory/'stdout.log').open('wb') as out, (directory/'stderr.log').open('wb') as err:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=out, stderr=err,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    save('launch.json', {'pid': process.pid, 'command': command, 'config': str(directory/'config.json')})
    print(json.dumps({'pid': process.pid, 'directory': str(directory), 'initial_scene': scenes[0]}))
    if args.open_panel:
        open_panel_when_ready(process, directory/'stdout.log')


if __name__ == '__main__':
    main()
