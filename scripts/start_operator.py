"""Start the local operator UI with the explicit Acer audience scene list."""
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage_display import AUDIENCE_DPI_ENV, configure_audience_dpi


if __name__ == '__main__':
    os.environ.update(AUDIENCE_DPI_ENV)
    configure_audience_dpi()
    os.chdir(ROOT)
    sys.argv = [str(ROOT / 'manager.py'), '--config', str(ROOT / 'configs/rebirth_operator_acer_xiaomi.json'),
                '--report-dir', str(ROOT / 'test_reports' / time.strftime('operator_%Y%m%d_%H%M%S')),
                '--operator-host', '127.0.0.1', '--operator-port', '8766']
    runpy.run_path(str(ROOT / 'manager.py'), run_name='__main__')
