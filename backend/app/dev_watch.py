"""Development-only source/config reload, without rebuilding container images."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

COMMANDS = {
    'api': ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
    'worker': ['celery', '-A', 'app.tasks.celery', 'worker', '--loglevel=info', '--concurrency=2'],
    'beat': ['celery', '-A', 'app.tasks.celery', 'beat', '--loglevel=info', '--schedule=/tmp/celerybeat-schedule'],
}


def snapshot():
    paths = list(Path('/app/app').rglob('*.py'))
    paths.append(Path(os.environ.get('WARDROBE_ENV_FILE', '/app/.env')))
    result = []
    for path in sorted(paths):
        try:
            stat = path.stat()
            result.append((str(path), stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            continue
    return tuple(result)


def main():
    service = sys.argv[1]
    command = [sys.executable, '-m', *COMMANDS[service]]
    stopping = False
    child = None

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if child and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        baseline = snapshot()
        child = subprocess.Popen(command)
        print(f'[dev-watch] {service} started; watching source and config', flush=True)
        changed = None
        reloading = False
        while child.poll() is None and not stopping:
            time.sleep(1)
            current = snapshot()
            if current == baseline:
                changed = None
            elif current != changed:
                changed = current
            else:
                # Debounce saves and let Celery finish in-flight tasks before reloading.
                print(f'[dev-watch] {service} source/config changed; reloading', flush=True)
                reloading = True
                child.terminate()
                break
        if stopping or reloading:
            child.wait()
        elif child.returncode:
            return child.returncode
        elif not stopping:
            return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
