"""Start the existing Manager; hold the production singleton for its lifetime."""
import argparse
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage_display import AUDIENCE_DPI_ENV, configure_audience_dpi


@contextmanager
def operator_session():
    """Prevent a retry from acquiring the camera before the first HTTP bind.

    A live handle keeps this named object present even if the convenience
    launcher times out. Windows closes it on process exit, including a crash.
    """
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, 'Local\\Rebirth2026OperatorSession')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    exists = ctypes.get_last_error() == 183
    try:
        if exists:
            raise RuntimeError('A production operator session is already running or starting. '
                               'No camera was opened. Use its panel/logs before retrying.')
        yield
    finally:
        kernel.CloseHandle(mutex)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'configs/rebirth_operator_acer_xiaomi.json')
    args = parser.parse_args()
    config_path = args.config.resolve()
    with operator_session():
        os.environ.update(AUDIENCE_DPI_ENV)
        configure_audience_dpi()
        os.chdir(ROOT)
        sys.argv = [str(ROOT/'manager.py'), '--config', str(config_path),
                    '--report-dir', str(ROOT/'test_reports'/time.strftime('operator_%Y%m%d_%H%M%S')),
                    '--operator-host', '127.0.0.1', '--operator-port', '8766']
        runpy.run_path(str(ROOT/'manager.py'), run_name='__main__')


if __name__ == '__main__':
    main()
