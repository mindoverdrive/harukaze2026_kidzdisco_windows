"""Acer-only verification entrypoint. Production configuration is never written."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_LOGS = ROOT / 'test_reports/face-check'


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def clean_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('KIDZDISCO_', 'HARUKAZE_', 'MATAHARI_FACE_', 'SDL_'))}
    env.update(PYTHONUTF8='1', PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1', SDL_AUDIODRIVER='dummy')
    return env


def code_version():
    def git(*args):
        p = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, encoding='utf-8', timeout=5)
        return p.stdout.strip() if p.returncode == 0 else 'unavailable'
    paths = [p for p in ROOT.rglob('*.py') if '.git' not in p.parts and '__pycache__' not in p.parts]
    return {'head': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'),
            'status': git('status', '--porcelain=v1', '--untracked-files=all'),
            'python_sources_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def camera_activity():
    """Windows privacy history is evidence, not an authoritative ownership API."""
    if os.name != 'nt':
        return {'state': 'unknown', 'apps': []}
    import winreg
    apps = []
    base = r'Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam'
    def visit(key, label):
        try:
            started = winreg.QueryValueEx(key, 'LastUsedTimeStart')[0]
            stopped = winreg.QueryValueEx(key, 'LastUsedTimeStop')[0]
            if started and not stopped:
                apps.append(label.replace('#', '\\').split('\\')[-1])
        except OSError:
            pass
        i = 0
        while True:
            try:
                name = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            with winreg.OpenKey(key, name) as child:
                visit(child, name)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as key:
            visit(key, 'webcam')
    except OSError:
        return {'state': 'unknown', 'apps': []}
    return {'state': 'reported_in_use' if apps else 'no_active_report_not_proof', 'apps': sorted(set(apps))}


def inspect_environment():
    result = {'python': sys.executable, 'python_version': sys.version, 'packages': {}, 'errors': [],
              'camera_opened': False, 'network_required': False, 'face_recognition_validated': False}
    for name in ('numpy', 'opencv-contrib-python', 'mediapipe', 'pygame', 'pygame-ce', 'screeninfo', 'pygrabber'):
        try:
            result['packages'][name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result['packages'][name] = None
    try:
        import cv2
        import pygame
        from face_morph_app import draw_meshes
        from face_morph_test_input import SyntheticLandmarkDetector
        result['pygame_import_version'] = pygame.version.ver
        result['camera_free_available'] = True
    except Exception as exc:
        result['camera_free_available'] = False
        result['errors'].append(f'描画依存不足: {type(exc).__name__}: {exc}')
    try:
        from stage_display import configure_audience_dpi
        result['dpi'] = configure_audience_dpi()
        from screeninfo import get_monitors
        result['monitors'] = [{k: getattr(m, k) for k in ('name', 'x', 'y', 'width', 'height', 'is_primary')} for m in get_monitors()]
    except Exception as exc:
        result['monitors'] = []
        result['errors'].append(f'表示列挙失敗: {exc}')
    try:
        from shared_camera import enumerate_camera_devices
        result['cameras'] = enumerate_camera_devices()
    except Exception as exc:
        result['cameras'] = []
        result['errors'].append(f'カメラ列挙失敗: {exc}')
    result['camera_activity'] = camera_activity()
    result['model_available'] = False
    try:
        import mediapipe as mp
        import numpy as np
        assets = ('modules/face_landmark/face_landmark_front_cpu.binarypb',
                  'modules/face_landmark/face_landmark.tflite',
                  'modules/face_detection/face_detection_short_range.tflite')
        base = Path(mp.__file__).parent
        result['model_assets'] = []
        for name in assets:
            p = base / name
            if not p.is_file() or not p.stat().st_size:
                raise FileNotFoundError(p)
            result['model_assets'].append({'path': str(p), 'bytes': p.stat().st_size,
                                           'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
        # Solutions FaceMesh reads these bundled assets; never calls a downloader.
        with mp.solutions.face_mesh.FaceMesh(max_num_faces=5, refine_landmarks=False) as detector:
            detector.process(np.zeros((240, 320, 3), dtype=np.uint8))
        result['model_available'] = True
        result['detector_blank_image_processed'] = True
    except Exception as exc:
        result['errors'].append(f'モデル不足・初期化失敗: {type(exc).__name__}: {exc}')
    result['code'] = code_version()
    return result


def isolated_config(settings):
    import manager
    config = dict(manager.DEFAULT_CONFIG)
    monitor = settings['monitor']
    config.update(SCENE_DIR=str(ROOT), PRODUCTION_SCENES=['face_morph_acer.py'],
                  TRANSITION_ENABLED=False, CLAP_MONITOR_ENABLED=False, PRELOAD_COUNT=0,
                  SHARED_CAMERA_ENABLED=True, DISPLAY_TARGET='stage',
                  DISPLAY_X=monitor['x']+40, DISPLAY_Y=monitor['y']+40,
                  DISPLAY_WIDTH=min(1100, monitor['width']-80), DISPLAY_HEIGHT=min(720, monitor['height']-120))
    return config


def run_session(directory):
    """Reuse production relay/SceneManager/wrapper/app/cleanup; change input only."""
    directory = Path(directory).resolve()
    settings = json.loads((directory/'settings.json').read_text(encoding='utf-8'))
    mode = settings['mode']
    from stage_display import configure_audience_dpi
    configure_audience_dpi()
    import manager
    import shared_camera
    from runtime_diagnostics import RuntimeDiagnostics
    from face_morph_test_input import SyntheticCapture
    shared_camera.SESSION_INFO_PATH = str(directory/'shared-camera.json')
    manager.CONFIG = isolated_config(settings)
    cfg = manager.CONFIG
    write_json(directory/'isolated-config.json', cfg)
    write_json(directory/'code-version.json', code_version())
    diagnostics = RuntimeDiagnostics(directory/'runtime', cfg)
    relay = scene = None
    result = {'mode': mode, 'physical_camera_tested': False, 'face_recognition_validated': False,
              'exit_reason': 'startup_error', 'cleanup_ok': False}
    started = time.monotonic()
    exit_code = 0
    try:
        diagnostics.record('verification_start', mode=mode, settings=settings,
                           input_kind='synthetic_landmarks' if mode == 'synthetic' else 'real_detector',
                           images_saved=False)
        if mode == 'camera':
            activity = camera_activity()
            if activity['apps']:
                raise RuntimeError('CAMERA_IN_USE: Windowsが使用中と報告: ' + ', '.join(activity['apps']))
            devices = shared_camera.enumerate_camera_devices()
            index = settings['camera_index']
            if index >= len(devices) or devices[index] != settings['camera_name']:
                raise RuntimeError('CAMERA_MISSING: カメラ構成が変わりました。一覧を更新してください。')
            relay = shared_camera.SharedCameraRelay(index, 1280, 720, 30, backend_preference='dshow',
                      strict_backend=True, fallback_to_default=False, explicit_index=index,
                      camera_name_hint=[settings['camera_name']], require_name_match=True, diagnostic_seconds=.25)
        else:
            class TestRelay(shared_camera.SharedCameraRelay):
                def _create_capture(self):
                    self.cap = SyntheticCapture(self.width, self.height, self.fps)
                    return self.cap
            # Index validation enumerates only; this input source never opens VideoCapture.
            relay = TestRelay(0, 960, 540, 30, diagnostic_seconds=.1)
        try:
            relay.start()
        except Exception as exc:
            reason = 'CAMERA_FIRST_FRAME_FAILED' if 'frame' in str(exc).lower() else 'CAMERA_OPEN_FAILED'
            raise RuntimeError(f'{reason}: {exc}（使用中・権限・接続を確認して再試行）') from exc
        deadline = time.monotonic()+8
        while relay.frame_id == 0 and time.monotonic() < deadline:
            if (directory/'stop.request').exists():
                raise RuntimeError('起動中に終了操作を受け付けました。')
            time.sleep(.02)
        if relay.frame_id == 0:
            raise RuntimeError('CAMERA_FIRST_FRAME_FAILED: 開いた後に画像が届きません。再接続・使用アプリ・権限を確認。')
        result['physical_camera_tested'] = mode == 'camera'
        env = relay.export_env()
        from stage_display import AUDIENCE_DPI_ENV
        env.update(AUDIENCE_DPI_ENV)
        env.update(MATAHARI_FACE_CHECK='1', MATAHARI_FACE_CHECK_WINDOWED='1',
                   MATAHARI_FACE_INPUT='synthetic_landmarks' if mode == 'synthetic' else 'detector',
                   MATAHARI_FACE_CHECK_DISPLAY=('合成ランドマーク・顔認識未検証' if mode == 'synthetic'
                         else '合成画像→実検出器・人物検出未検証' if mode == 'detector'
                         else '内蔵／選択カメラ1人確認・実5人未検証') + (' / PC画面のみ' if settings['monitor']['is_primary'] else ' / 選択画面・本番未受入'))
        scene = manager.SceneManager(camera_env=env, scenes=[str(ROOT/'face_morph_acer.py')], diagnostics=diagnostics)
        if not scene.request_scene('next'):
            raise RuntimeError('Manager rejected initial launch')
        next_sample = 0
        shown = None
        while True:
            now = time.monotonic()
            scene.tick()
            if scene.fatal_error or scene.last_switch_error:
                raise RuntimeError(scene.fatal_error or scene.last_switch_error)
            if relay.thread and not relay.thread.is_alive():
                raise RuntimeError('共有入力スレッド停止: ' + str(relay.last_error))
            if now >= next_sample:
                diagnostics.sample(relay, scene)
                next_sample = now+1
                write_json(directory/'progress.json', {'elapsed': now-started, 'promotions': scene.completed_promotions,
                                                      'running': scene.is_scene_running(), 'camera_frame_id': relay.frame_id})
            if scene.completed_promotions and shown is None:
                shown = now
            if (directory/'stop.request').exists():
                result['exit_reason'] = 'operator_stop'
                break
            if shown is not None and not scene.is_scene_running():
                code = scene.running_process.poll() if scene.running_process else None
                result.update(exit_reason='scene_closed', scene_exit_code=code)
                if code not in (0, None):
                    raise RuntimeError(f'口meshが異常終了しました: code={code}')
                break
            if shown is not None and settings.get('duration', 0) and now-shown >= settings['duration']:
                result['exit_reason'] = 'duration_complete'
                break
            time.sleep(.01)
        result['promotions'] = scene.completed_promotions
    except BaseException as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
        diagnostics.record('verification_error', message=result['error'])
        print(result['error'], flush=True)
        exit_code = 1
    finally:
        checks = []
        for label, owner in (('manager', scene), ('relay', relay)):
            if owner is not None:
                try:
                    checks.append((label, owner.cleanup() if label == 'manager' else owner.close()))
                except BaseException as exc:
                    checks.append((label, False))
                    result[label+'_cleanup_error'] = str(exc)
        result.update(cleanup_ok=all(ok for _, ok in checks), cleanup=checks, elapsed=time.monotonic()-started)
        diagnostics.record('verification_end', **result)
        result['logs_closed'] = diagnostics.close()
        write_json(directory/'result.json', result)
    return exit_code if result['cleanup_ok'] and result['logs_closed'] else 1


def finish_owned_child(process, output, label, reason):
    """Retain caller ownership until the existing Manager stop and log close succeed."""
    from manager import SceneManager
    try:
        stopper = SceneManager(scenes=[])
        if not stopper._kill_process(process, label, reason=reason):
            return False, '所有プロセスの停止を確認できません。再試行します。'
        output.close()
        return True, None
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'


def begin_gui_stop(state):
    # The deadline must exist even when the graceful request cannot be saved.
    state['stopping'] = time.monotonic()
    try:
        (state['session']/'stop.request').touch()
    except OSError as exc:
        state['stop_request_error'] = f'{type(exc).__name__}: {exc}'
        return state['stop_request_error']
    return None


def finish_gui_worker(state, *, forced=False):
    if forced and not state['forced_stop_logged']:
        # Observation failures must not prevent the owned stop or its retries.
        state['forced_stop_logged'] = True
        try:
            write_json(state['session']/'forced-stop.json',
                       {'forced': True, 'reason': 'graceful_stop_timeout',
                        'scope': 'owned verification job only'})
        except OSError as exc:
            state['stop_log_error'] = f'{type(exc).__name__}: {exc}'
    return finish_owned_child(state['process'], state['output'],
                              'face-check worker', 'verification_worker_end')


def poll_with_retry(window, callback, update, on_error):
    try:
        update()
    except Exception as exc:
        on_error(exc)
    finally:
        if window.winfo_exists():
            window.after(250, callback)


def gui(log_root):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from windows_process import WindowsSceneJob, get_scene_job
    window = tk.Tk()
    window.title('MATAHARI 口mesh確認')
    window.geometry('850x620')
    state = {'process': None, 'job': None, 'output': None, 'session': None, 'inspection': None,
             'inspection_process': None, 'inspection_started': 0, 'stopping': None,
             'inspection_stopping': False, 'inspection_error': None, 'startup_error': None,
             'forced_stop_logged': False, 'stop_request_error': None, 'stop_log_error': None}
    root_logs = Path(log_root)
    root_logs.mkdir(parents=True, exist_ok=True)
    def new_dir(prefix):
        stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y%m%d-%H%M%S-%f')
        p = root_logs/(prefix+'-'+stamp)
        p.mkdir()
        return p
    status = tk.StringVar(value='環境を確認しています。カメラは開きません。')
    ttk.Label(window, text='MATAHARI 口mesh確認', font=('Yu Gothic UI', 18)).pack(anchor='w', padx=18, pady=10)
    ttk.Label(window, text='基本操作：カメラなしテスト → ウィンドウで確認 → ESCで終了 → もう一度開始\n合成ランドマークは顔認識を検証しません。顔写真・動画を保存しません。').pack(anchor='w', padx=18)
    controls = ttk.Frame(window)
    controls.pack(fill='x', padx=18, pady=10)
    ttk.Label(controls, text='表示先').grid(row=0, column=0, sticky='w')
    displays = ttk.Combobox(controls, state='readonly', width=65)
    displays.grid(row=0, column=1, pady=5)
    ttk.Label(controls, text='カメラ（任意）').grid(row=1, column=0, sticky='w')
    cameras = ttk.Combobox(controls, state='readonly', width=65)
    cameras.grid(row=1, column=1, pady=5)
    free = tk.BooleanVar(value=False)
    ttk.Checkbutton(window, text='カメラを使う場合：他のカメラ使用アプリを終了した', variable=free).pack(anchor='w', padx=18)
    buttons = ttk.Frame(window)
    buttons.pack(fill='x', padx=18, pady=12)
    text = tk.Text(window, height=15, wrap='word', font=('Yu Gothic UI', 10))
    text.pack(fill='both', expand=True, padx=18, pady=8)
    ttk.Label(window, textvariable=status, wraplength=810).pack(anchor='w', padx=18, pady=10)
    def report(value):
        text.insert('end', value+'\n')
        text.see('end')
    def refresh():
        if state['process'] or state['inspection_process']:
            return
        target = new_dir('environment')
        output = (target/'preflight.log').open('wb')
        try:
            p = subprocess.Popen([sys.executable, '-B', __file__, '--inspect', str(target/'environment.json')],
                                 cwd=ROOT, env=clean_env(), stdout=output, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except BaseException:
            output.close()
            raise
        # Keep the exact Popen object before Job assignment can partially fail.
        state.update(inspection_process=p, inspection_output=output, inspection_target=target,
                     inspection_started=time.monotonic(), inspection_job=None, inspection=None,
                     inspection_stopping=False, inspection_error=None)
        try:
            state['inspection_job'] = WindowsSceneJob(p) if os.name == 'nt' else None
        except Exception as exc:
            state.update(inspection_job=get_scene_job(p), inspection_stopping=True,
                         inspection_error=f'環境確認の所有登録失敗: {exc}')
            status.set(state['inspection_error']+'。所有範囲を回収しています。')
            return
        status.set('環境・ローカルモデル・機器一覧を確認中（カメラ未使用）')
    def start(mode):
        if state['process'] or state['inspection_process']:
            return
        info = state['inspection']
        if not info or not info.get('camera_free_available') or not info.get('monitors'):
            messagebox.showerror('環境未確認', '環境確認・更新を実行し、エラーを確認してください。')
            return
        if mode != 'synthetic' and not info.get('model_available'):
            messagebox.showerror('モデル不足', 'ローカルモデル初期化に失敗しました。環境ログを確認してください。自動ダウンロードは行いません。')
            return
        if mode == 'camera':
            if not info['cameras'] or cameras.current() < 0:
                messagebox.showerror('カメラ未接続', 'カメラ一覧を更新してください。カメラなしテストは実行できます。')
                return
            if not free.get():
                messagebox.showinfo('カメラ使用確認', '他の使用アプリを終了してチェックを入れてください。')
                return
            activity = camera_activity()
            if activity['apps']:
                messagebox.showerror('カメラ使用中の記録', ', '.join(activity['apps'])+'\n該当アプリを終了して再試行してください。')
                return
        monitor = info['monitors'][max(displays.current(), 0)]
        settings = {'mode': mode, 'monitor': monitor, 'camera_index': max(cameras.current(), 0),
                    'camera_name': cameras.get(), 'duration': 0, 'started_at': dt.datetime.now().astimezone().isoformat()}
        directory = new_dir(mode)
        write_json(directory/'settings.json', settings)
        write_json(directory/'environment.json', info)
        output = (directory/'launcher.log').open('wb')
        try:
            p = subprocess.Popen([sys.executable, '-B', __file__, '--run', str(directory)], cwd=ROOT,
                                 env=clean_env(), stdout=output, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except BaseException:
            output.close()
            raise
        state.update(process=p, job=None, output=output, session=directory, stopping=None,
                     startup_error=None, forced_stop_logged=False,
                     stop_request_error=None, stop_log_error=None)
        try:
            state['job'] = WindowsSceneJob(p) if os.name == 'nt' else None
        except Exception as exc:
            state.update(job=get_scene_job(p), stopping=time.monotonic(),
                         startup_error=f'確認プロセスの所有登録失敗: {exc}')
            status.set(state['startup_error']+'。所有範囲を回収しています。')
            return
        status.set('起動中。確認画面はESCで終了できます。')
        report(f'開始: {mode}\nログ: {directory}')
    def stop():
        if state['process'] and state['stopping'] is None:
            error = begin_gui_stop(state)
            status.set('終了要求を保存できません。期限後に所有プロセスを回収します: '+error
                       if error else 'Manager経由で終了・回収しています。')
    def poll_once():
        p = state['inspection_process']
        if p:
            if p.poll() is None and time.monotonic()-state['inspection_started'] > 45:
                state.update(inspection_stopping=True, inspection_error='環境確認が時間切れ。ログを確認して再試行してください。')
            if state['inspection_stopping'] or p.poll() is not None:
                closed, error = finish_owned_child(p, state['inspection_output'], 'face-check environment', 'verification_inspection_end')
                if not closed:
                    status.set('環境確認の回収を再試行中: '+str(error))
                    return
                state.update(inspection_process=None, inspection_job=None, inspection_output=None,
                             inspection_stopping=False)
                path = state['inspection_target']/'environment.json'
                if path.exists() and not state['inspection_error'] and p.returncode == 0:
                    info = json.loads(path.read_text(encoding='utf-8'))
                    state['inspection'] = info
                    displays['values'] = [f"{m['name']} {m['width']}x{m['height']} {'PC画面のみ' if m['is_primary'] else '外部画面・本番未受入'}" for m in info['monitors']]
                    if info['monitors']:
                        displays.current(next((i for i,m in enumerate(info['monitors']) if m['is_primary']), 0))
                    cameras['values'] = info['cameras']
                    if info['cameras']:
                        cameras.current(next((i for i,n in enumerate(info['cameras']) if 'user facing' in n.lower() or 'integrated' in n.lower()), 0))
                    report(f"Python: {info['python_version'].splitlines()[0]}\n{info['python']}\nカメラなし: {info['camera_free_available']} / ローカル検出器: {info['model_available']}\nカメラ: {', '.join(info['cameras']) or '未接続／列挙不可'}")
                    for error in info['errors']:
                        report(error)
                    status.set('準備完了。最初は「カメラなしテスト」を選択してください。')
                else:
                    status.set(state['inspection_error'] or f"環境確認失敗。ログ: {state['inspection_target']}")
        p = state['process']
        if p:
            overdue = state['stopping'] is not None and time.monotonic()-state['stopping'] > 12
            if state['startup_error'] or overdue or p.poll() is not None:
                closed, error = finish_gui_worker(state, forced=overdue)
                if not closed:
                    status.set('確認プロセスの回収を再試行中: '+str(error))
                    return
                state.update(process=None, job=None, output=None, stopping=None)
                path = state['session']/'result.json'
                result = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'error': '終了記録なし・launcher.log参照', 'cleanup_ok': False}
                if state['startup_error']:
                    result['launcher_error'] = state['startup_error']
                for key in ('stop_request_error', 'stop_log_error'):
                    if state[key]:
                        result[key] = state[key]
                report('終了: '+json.dumps(result, ensure_ascii=False))
                success=result.get('cleanup_ok') and result.get('logs_closed') and not result.get('error') and not state['startup_error'] and not state['forced_stop_logged'] and p.returncode==0
                status.set('終了しました。再起動可能です。' if success else 'エラーまたは回収未確認。ログを確認して環境確認から再試行してください。')
                state['startup_error'] = None
            elif state['stopping'] is None:
                progress_path = state['session']/'progress.json'
                if progress_path.exists():
                    progress = json.loads(progress_path.read_text(encoding='utf-8'))
                    if progress.get('promotions') and progress.get('running'):
                        status.set(f"表示中（{progress.get('elapsed', 0):.0f}秒）。確認画面はESCで終了できます。")
    def poll_error(exc):
        status.set(f'状態確認・回収を再試行します: {type(exc).__name__}: {exc}')
    def poll():
        poll_with_retry(window, poll, poll_once, poll_error)
    def close():
        if state['process']:
            stop()
            window.after(300, close)
        elif state['inspection_process']:
            state['inspection_stopping'] = True
            window.after(300, close)
        else:
            window.destroy()
    ttk.Button(buttons, text='カメラなしテスト', command=lambda: start('synthetic')).pack(side='left', padx=3)
    ttk.Button(buttons, text='画像→実検出器（顔なし）', command=lambda: start('detector')).pack(side='left', padx=3)
    ttk.Button(buttons, text='内蔵／選択カメラ1人確認', command=lambda: start('camera')).pack(side='left', padx=3)
    ttk.Button(buttons, text='終了', command=stop).pack(side='left', padx=3)
    ttk.Button(buttons, text='環境確認・更新', command=refresh).pack(side='left', padx=3)
    report('手順: 閉じる→1回開くと変身→閉じて次へ→1〜5人→交差→遮蔽→退出・復帰（約40秒周期）。\n描画は既存OpenCV CPU＋Pygame SDL。GPUによるメッシュ演算の試験ではありません。\nカメラ試験: 閉じる→1回開く→開けたまま保持→閉じて再度開く→短い見失い→復帰→終了→再起動。\nカメラが開かない: 他の使用アプリ・Windows権限・接続を確認し「環境確認・更新」。\n初回画像が届かない: 一度終了し接続と対応解像度を確認。モデル不足: 確認済み環境のローカル資産を復元。')
    window.protocol('WM_DELETE_WINDOW', close)
    refresh()
    poll()
    window.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--logs', type=Path, default=DEFAULT_LOGS)
    args = parser.parse_args()
    if args.inspect:
        write_json(args.inspect, inspect_environment())
        return 0
    if args.run:
        return run_session(args.run)
    # Hold a local named mutex for the launcher lifetime; no cross-app termination.
    handle = None
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateMutexW(None, False, 'Local\\MATAHARI_FaceMesh_Verification')
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            kernel.CloseHandle(handle)
            # A blocking dialog from a minimized shortcut can be invisible and
            # leave another interpreter waiting. Return without starting Tk.
            print('MATAHARI 口mesh確認は既に起動しています。既存ウィンドウを使用してください。')
            return 0
    try:
        gui(args.logs)
    finally:
        if handle:
            kernel.CloseHandle(handle)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
