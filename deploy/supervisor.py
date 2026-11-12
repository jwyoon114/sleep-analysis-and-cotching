"""Run both servers; propagate shutdown and fail if either child exits."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def run(commands, env, cwd=ROOT, grace=20):
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    code = 0
    try:
        for command in commands:
            children.append(subprocess.Popen(command, cwd=cwd, env=env))
        while not stopping:
            if any(child.poll() is not None for child in children):
                print("A server exited; stopping service.", flush=True)
                code = 1
                break
            time.sleep(0.1)
    except Exception:
        print("Service startup failed.", file=sys.stderr, flush=True)
        code = 1
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + grace
        for child in children:
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return code


def main():
    sys.path.insert(0, str(ROOT))
    from production_policy import check_configuration
    env = os.environ.copy()
    try:
        check_configuration(env)
        port = int(env.get("PORT", "10000"))
        if not 1 <= port <= 65535 or port == 8011:
            raise ValueError
        if env.get("SLEEP_DB_BACKEND") != "postgresql" or not env.get("DATABASE_URL"):
            raise ValueError
        if env.get("COACHING_ENGINE", "rules") != "rules":
            raise ValueError
    except ValueError:
        print("Check PORT, PostgreSQL configuration and rules engine.", file=sys.stderr)
        return 1
    env.update(PORT=str(port), HOSTNAME="0.0.0.0", SLEEP_API_URL="http://127.0.0.1:8011",
               COACHING_ENGINE="rules", SLEEP_DESKTOP_ALARMS="0")
    for key in list(env):
        if key.startswith('OPENAI_'):
            env.pop(key)
    # One authoritative runner, before any listening socket is opened.
    from postgres_migrate import apply_migrations
    try:
        apply_migrations()
    except Exception:
        print('PostgreSQL migration verification failed; service was not started.', file=sys.stderr)
        return 1
    return run([
        [sys.executable, "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8011",
         "--timeout-graceful-shutdown", "15", "--no-access-log"],
        ["node", str(ROOT / "web/server.js")],
    ], env)


if __name__ == "__main__":
    sys.exit(main())
