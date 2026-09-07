"""Observe Windows GPU memory outside the scene process; never declares a pass."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime_diagnostics import process_sample

QUERY = "Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory -ErrorAction Stop | Select-Object Name,DedicatedUsage,SharedUsage | ConvertTo-Json -Compress"


def gpu_counters():
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', QUERY],
                            capture_output=True, text=True, timeout=15, check=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    data = json.loads(result.stdout) if result.stdout.strip() else []
    return [data] if isinstance(data, dict) else data


def match_counters(identity, before, after, counters):
    result = dict(pid=identity['pid'], creation_ticks=identity.get('creation_ticks'),
                  dedicated_bytes=None, shared_bytes=None)
    expected = identity.get('creation_ticks')
    if expected is None or before.get('creation_ticks') != expected or after.get('creation_ticks') != expected:
        return dict(result, unavailable='Process exited, PID reused, or identity unavailable')
    matches = {}
    for row in counters:
        name = row.get('Name', '')
        match = re.match(r'^pid_(\d+)_', name)
        if match and int(match.group(1)) == identity['pid']:
            matches[name] = row
    if not matches:
        return dict(result, unavailable='No GPU counter instance; not equivalent to zero usage')
    if any(row.get(key) is None for row in matches.values() for key in ('DedicatedUsage', 'SharedUsage')):
        return dict(result, unavailable='Incomplete GPU counter values')
    return dict(result, dedicated_bytes=sum(int(r['DedicatedUsage']) for r in matches.values()),
                shared_bytes=sum(int(r['SharedUsage']) for r in matches.values()), instances=list(matches))


def observe(trial):
    # Current rotating log contains the most recent sample/end. Ignore a partially written line.
    rows = []
    for line in (trial/'runtime.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if rows and rows[-1].get('event') == 'run_end':
        return {'event': 'trial_ended', 'run_end': rows[-1]}
    latest = next((r for r in reversed(rows) if r.get('event') == 'sample'), None)
    if latest is None:
        return {'event': 'waiting_for_sample'}
    identities = latest.get('processes', [])
    before = {p['pid']: process_sample(p['pid']) for p in identities}
    started = time.monotonic()
    counters = gpu_counters()
    results = [match_counters(p, before[p['pid']], process_sample(p['pid']), counters) for p in identities]
    return {'event': 'gpu_sample', 'runtime_elapsed_s': latest['elapsed_s'],
            'query_seconds': round(time.monotonic()-started, 3), 'processes': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--interval', type=float, default=60)
    parser.add_argument('--samples', type=int, default=720)
    args = parser.parse_args()
    if args.interval < 10 or not 1 <= args.samples <= 10000:
        parser.error('interval must be >=10 seconds; samples must be 1..10000')
    if not (args.trial/'runtime.jsonl').is_file():
        parser.error('trial must contain runtime.jsonl')
    output = args.trial/('gpu_observation_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jsonl')
    with output.open('x', encoding='utf-8') as file:
        for index in range(args.samples):
            try:
                result = observe(args.trial)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                result = {'event': 'gpu_unavailable', 'reason': type(exc).__name__}
            result['wall_time'] = datetime.now(timezone.utc).isoformat()
            file.write(json.dumps(result) + '\n')
            file.flush()
            print(json.dumps(result), flush=True)
            if result['event'] == 'trial_ended':
                break
            if index+1 < args.samples:
                time.sleep(args.interval)
    print('GPU observation: ' + str(output))


if __name__ == '__main__':
    main()
