"""Run premium browser flows against a fresh loopback TLS PostgreSQL database."""

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "sleep_frontend"
sys.path.insert(0, str(ROOT))

from postgres_migration_fixture import PostgresTestCluster
from postgres_migrate import apply_migrations


class FixtureLifetime(unittest.TestCase):
    pass


def free_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("staging", "production"), default="staging")
    args = parser.parse_args()
    pg_bin = os.getenv("DALJAM_TEST_POSTGRES_BIN")
    node = shutil.which("node")
    server = WEB / ".next-production" / "standalone"
    if not pg_bin or not node or not (server / "server.js").is_file():
        raise RuntimeError("Set test PostgreSQL binaries and build .next-production before this local check")
    runtime = WEB / ".runtime"
    runtime.mkdir(exist_ok=True)
    with ExitStack() as stack:
        stack.callback(FixtureLifetime.doClassCleanups)
        cluster = PostgresTestCluster(FixtureLifetime, Path(pg_bin))
        database = cluster.url(cluster.new_database())
        # The sole DB URL comes from the disposable loopback fixture.
        os.environ["DATABASE_URL"] = database
        assert apply_migrations() == (1, 2, 3, 4)
        assert apply_migrations() == ()
        api_port, web_port = free_port(), free_port()
        while api_port == web_port:
            web_port = free_port()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("PG", "OPENAI_"))
               and key not in {"DATABASE_URL", "SLEEP_DB_PATH", "DALJAM_PUBLIC_ORIGIN"}}
        env.update(DATABASE_URL=database, SLEEP_DB_BACKEND="postgresql", SLEEP_DESKTOP_ALARMS="0",
                   DALJAM_ENV=args.mode, DALJAM_PREMIUM_DEMO="1", DALJAM_DEMO_ONLY="0", COACHING_ENGINE="openai",
                   COACHING_USER_LIMIT_24H="0", COACHING_GLOBAL_LIMIT_24H="0", HOSTNAME="127.0.0.1",
                   PORT=str(web_port), SLEEP_API_URL=f"http://127.0.0.1:{api_port}", NEXT_TELEMETRY_DISABLED="1",
                   PREMIUM_TEST_ENV=args.mode, DALJAM_PREMIUM_TEST_ORIGIN=f"http://127.0.0.1:{web_port}")
        shutil.copytree(WEB / "public", server / "public", dirs_exist_ok=True)
        shutil.copytree(WEB / ".next-production" / "static", server / ".next-production" / "static", dirs_exist_ok=True)

        def start(command, cwd, name, process_env):
            log = stack.enter_context((runtime / name).open("wb"))
            process = subprocess.Popen(command, cwd=cwd, env=process_env, stdout=log, stderr=subprocess.STDOUT)
            def stop():
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=15)
            stack.callback(stop)
            return process

        # A regression cannot reach a real provider, even if a local secret file exists.
        api_code = f"""
import coaching_service
import uvicorn

def forbid_provider():
    raise AssertionError('External AI is forbidden')

coaching_service.settings = forbid_provider
uvicorn.run('api:app', host='127.0.0.1', port={api_port}, access_log=False)
"""
        api = start([sys.executable, "-B", "-c", api_code], ROOT, f"premium-api-{args.mode}.log", env)
        web_env = {key: value for key, value in env.items() if key != "DATABASE_URL"}
        web = start([node, "server.js"], server, f"premium-web-{args.mode}.log", web_env)
        for _ in range(80):
            if api.poll() is not None or web.poll() is not None:
                raise RuntimeError("An isolated server stopped before readiness")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{web_port}/api/ready", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError("The isolated servers failed readiness")
        subprocess.run([node, str(WEB / "tests" / "premium-browser.mjs")], cwd=WEB, env=web_env, check=True)


if __name__ == "__main__":
    main()
