"""Release rehearsals using only a disposable loopback PostgreSQL cluster."""

from contextlib import contextmanager
from hashlib import sha256
from http.client import HTTPConnection
import json
import gzip
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from postgres_migration_fixture import PostgresTestCluster
import postgres_migrate


ROOT = Path(__file__).resolve().parents[1]
LEGACY = "76d51039bbafc7db6e46b12edaa1cbe862a0eb44"
ROLLBACK = json.loads((ROOT / 'deploy/rollback-source.json').read_text(encoding='utf-8'))
ROLLBACK_SOURCE = ROLLBACK['commit']
ORIGIN = "https://release-check.invalid"
PROFILE = {
    "mbti": "ISTJ", "speech": "polite", "intensity": "gentle",
    "allow_profanity": False, "character": "cat",
}
ACTIVITY = {"id": "synthetic-stretch", "title": "합성 계획"}
APK_SHA = "95d84e979b72d1f150c59c0cdb33a6d70fa63e0adbeba05ab57a64c699eae05e"


class LocalHTTP:
    def __init__(self, port):
        self.port = port
        self.cookie = None

    def request(self, path, method="GET", payload=None):
        headers = {"Origin": ORIGIN}
        if self.cookie:
            headers["Cookie"] = self.cookie
        if payload is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(payload).encode("ascii")
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, payload, headers)
            response = conn.getresponse()
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, headers, response.read()
        finally:
            conn.close()

    def json(self, route, method="GET", payload=None, status=200):
        actual, headers, body = self.request("/api/sleep/" + route, method, payload)
        if actual != status:
            raise AssertionError(f"{method} {route} returned {actual}, expected {status}")
        if route == "auth/login":
            self.cookie = headers["set-cookie"].split(";", 1)[0]
        return json.loads(body)

    def ready(self):
        for _ in range(90):
            try:
                if self.request("/api/ready")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(1)
        raise AssertionError("The production container did not become ready")


@unittest.skipUnless(os.getenv("DALJAM_TEST_POSTGRES_BIN"), "Set local PostgreSQL binaries for recovery")
class ReleaseRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = PostgresTestCluster(cls, Path(os.environ["DALJAM_TEST_POSTGRES_BIN"]))
        cls.workspace = Path(cls.enterClassContext(tempfile.TemporaryDirectory(prefix="daljam-rehearsal-")))
        archive = cls.workspace / "legacy.zip"
        subprocess.run(["git", "archive", "--format=zip", "-o", str(archive), LEGACY], cwd=ROOT, check=True)
        cls.legacy = cls.workspace / "legacy"
        with ZipFile(archive) as bundle:
            bundle.extractall(cls.legacy)
        cls.legacy_migrations = cls.legacy / "migrations" / "postgresql"
        rollback_archive = cls.workspace / 'rollback-source.zip'
        subprocess.run(['git', 'archive', '--format=zip', '-o', str(rollback_archive), ROLLBACK_SOURCE], cwd=ROOT, check=True)
        cls.rollback_source = cls.workspace / 'rollback-source'
        with ZipFile(rollback_archive) as bundle:
            bundle.extractall(cls.rollback_source)
        rollback_catalog = postgres_migrate.load_migrations(cls.rollback_source / 'migrations/postgresql')
        if ([entry.version for entry in rollback_catalog] != ROLLBACK['schema_versions']
                or rollback_catalog != postgres_migrate.load_migrations()[:len(rollback_catalog)]):
            raise AssertionError('Rollback migration catalog does not match the release prefix')
        for module in ('production_policy.py', 'backup_policy.py'):
            if (cls.rollback_source / module).read_text(encoding='utf-8') != (ROOT / module).read_text(encoding='utf-8'):
                raise AssertionError('Rollback policy does not match the release')
        cls.password = secrets.token_urlsafe(24)

    def isolated_env(self, database):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("PG", "OPENAI_")) and key not in
               {"DATABASE_URL", "SLEEP_DB_PATH", "DALJAM_TEST_PG_URL"}}
        env.update(DATABASE_URL=self.cluster.url(database), SLEEP_DB_BACKEND="postgresql",
                   DALJAM_ENV="production", DALJAM_DEMO_ONLY="0", DALJAM_PUBLIC_ORIGIN=ORIGIN,
                   DALJAM_BACKUP_POLICY="render-pitr-3d-v1", COACHING_ENGINE="rules",
                   SLEEP_DESKTOP_ALARMS="0", PYTHONDONTWRITEBYTECODE="1",
                   DALJAM_REHEARSAL_PASSWORD=self.password)
        return env

    def apply(self, database, catalog=postgres_migrate.MIGRATIONS):
        with patch.dict(os.environ, self.isolated_env(database), clear=True):
            return postgres_migrate.apply_migrations(catalog)

    def python(self, source, database, *args, status=0, marker=None):
        env = self.isolated_env(database)
        if Path(source).resolve() == self.legacy.resolve():
            # Test the unmodified legacy runtime with its own configuration.
            env['DALJAM_BACKUP_POLICY'] = 'render-pitr-7d-v1'
        result = subprocess.run([sys.executable, "-B", *args], cwd=source, env=env,
                                capture_output=True, text=True, encoding="utf-8", timeout=75)
        self.assertEqual(result.returncode, status, f"Unexpected exit in {args[0]}")
        if marker:
            self.assertIn(marker, result.stderr)
        return result.stdout

    def seed(self, database):
        self.assertEqual(self.apply(database, self.legacy_migrations), (1, 2))
        return json.loads(self.python(self.legacy, database, "-c", """
import json, os
from sleep_accounts import register
from production_policy import POLICY_VERSION
from health_records import import_export
from coaching_service import generate
from json_sleep import EXAMPLE_JSON
account = register('synthetic-recovery', os.environ['DALJAM_REHEARSAL_PASSWORD'], consent=POLICY_VERSION)
record, = import_export(EXAMPLE_JSON, 'synthetic-recovery.json', account['id'])['analysis_ids']
coaching = generate(account['id'], record, {})
print(json.dumps({'account': account, 'session': record, 'text': coaching['coaching']}))
"""))

    def snapshot(self, database, *, upgraded=False):
        with self.cluster.connect(database) as connection:
            tables = ["accounts", "account_consents", "sessions", "stages", "coaching", "coaching_context"]
            if upgraded:
                tables.extend(("account_personalization", "morning_plans", "daljam_schema_migrations",
                               "web_push_subscriptions", "web_push_test_limits", "web_push_deliveries"))
            return {table: connection.execute("SELECT * FROM " + table + " ORDER BY 1, 2").fetchall()
                    for table in tables}

    def rollback_with_current_catalog(self, name):
        destination = self.workspace / name
        shutil.copytree(self.rollback_source, destination)
        shutil.copytree(postgres_migrate.MIGRATIONS, destination / "migrations" / "postgresql", dirs_exist_ok=True)
        return destination

    def cli(self, program, database, *args):
        # The generated cluster is the only possible target. Keep passwords out of argv.
        executable = self.cluster.bin_dir / (program + (".exe" if os.name == "nt" else ""))
        env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        env.update(PGPASSWORD=self.cluster.password, PGSSLMODE="require")
        subprocess.run([str(executable), "--host=127.0.0.1", f"--port={self.cluster.port}",
                        f"--username={self.cluster.role}", f"--dbname={database}", "--no-password", *args],
                       env=env, check=True, capture_output=True, timeout=90)

    def old_api(self, root, database, seed, *, write=False):
        output = self.python(root, database, "-c", """
import json, os, sys
from fastapi.testclient import TestClient
from api import app
with TestClient(app) as client:
    client.get('/ready').raise_for_status()
    login = client.post('/auth/login', json={'username': 'synthetic-recovery',
                    'password': os.environ['DALJAM_REHEARSAL_PASSWORD']}).raise_for_status().json()
    headers = {'Authorization': 'Bearer ' + login['token']}
    history = client.get('/watch/sessions/' + sys.argv[1] + '/coaching', headers=headers).raise_for_status().json()
    if sys.argv[2] == 'write':
        client.post('/alarms', headers=headers, json={'bedtime': '23:15', 'wake_time': '07:00',
                    'timezone': 'Asia/Seoul', 'enabled': False}).raise_for_status()
    print(json.dumps({'account': login['user'], 'text': history['history'][0]['coaching']}))
""", seed["session"], "write" if write else "read")
        self.assertEqual(json.loads(output), {key: seed[key] for key in ("account", "text")})

    def test_backup_upgrade_restore_and_compatibility(self):
        from fastapi.testclient import TestClient
        from api import app

        database = self.cluster.new_database()
        seed = self.seed(database)
        before = self.snapshot(database)
        dump = self.workspace / "before-upgrade.dump"
        self.cli("pg_dump", database, "--format=custom", "--file=" + str(dump))
        self.assertGreater(dump.stat().st_size, 0)

        self.assertEqual(self.apply(database), (3, 4, 5, 6, 7, 8))
        self.assertEqual(self.apply(database), ())
        with patch.dict(os.environ, self.isolated_env(database), clear=True), TestClient(app) as http:
            token = http.post("/auth/login", json={
                "username": "synthetic-recovery", "password": self.password,
            }).raise_for_status().json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            http.post("/auth/personalization", json=PROFILE, headers=headers).raise_for_status()
            day = http.get("/plans", headers=headers).raise_for_status().json()["next_date"]
            http.post(f"/plans/{day}", json={"activities": [ACTIVITY]}, headers=headers).raise_for_status()
        after = self.snapshot(database, upgraded=True)
        self.assertTrue(after["account_personalization"] and after["morning_plans"])
        self.assertEqual({table: after[table] for table in before}, before)
        self.python(self.legacy, database, "deploy/supervisor.py", status=1, marker="migration verification failed")

        restored = self.cluster.new_database()
        self.cli("pg_restore", restored, "--exit-on-error", "--single-transaction",
                 "--no-owner", "--no-privileges", str(dump))
        self.assertEqual(self.snapshot(restored), before)
        self.assertEqual(self.apply(restored, self.legacy_migrations), ())
        self.old_api(self.legacy, restored, seed)

        self.python(self.rollback_source, database, "-m", "postgres_migrate", status=1, marker="앞선 마이그레이션")
        compatible = self.rollback_with_current_catalog("compatible")
        self.python(compatible, database, "-m", "postgres_migrate")
        self.old_api(compatible, database, seed, write=True)
        self.assertEqual(self.snapshot(database, upgraded=True), after)

    @unittest.skipUnless(os.getenv("DALJAM_TEST_RELEASE_DOCKER") == "1", "Opt in on Linux with Docker")
    def test_linux_production_images(self):
        self.assertEqual(sys.platform, "linux")
        tag = "daljam-rehearsal-" + secrets.token_hex(5)
        candidate, previous, compatible = (tag + ":" + label for label in ("candidate", "previous", "compatible"))
        subprocess.run(["docker", "build", "-f", "Dockerfile.production", "-t", candidate, "."],
                       cwd=ROOT, check=True, timeout=900)
        subprocess.run(["docker", "build", "-f", "Dockerfile.production", "-t", previous, "."],
                       cwd=self.legacy, check=True, timeout=900)
        subprocess.run(['docker', 'build', '-f', 'Dockerfile.production', '-t', compatible, '.'],
                       cwd=self.rollback_with_current_catalog("docker-compatible"), check=True, timeout=900)

        database = self.cluster.new_database()
        seed = self.seed(database)
        with socket.socket() as port:
            port.bind(("127.0.0.1", 0))
            http = LocalHTTP(port.getsockname()[1])
        env = self.isolated_env(database)
        env["PORT"] = str(http.port)
        args = ["--network", "host", "--env", "DATABASE_URL", "--env", "DALJAM_BACKUP_POLICY",
                "--env", "DALJAM_PUBLIC_ORIGIN", "--env", "PORT"]
        def docker(*command, **kwargs):
            return subprocess.run(["docker", *command], timeout=35, env=env, **kwargs)

        incomplete = docker("run", "--rm", "--network", "none", "--env", "DALJAM_BACKUP_POLICY",
                            "--env", "DALJAM_PUBLIC_ORIGIN", candidate, capture_output=True)
        self.assertEqual(incomplete.returncode, 1)
        self.assertIn(b"Check PORT, PostgreSQL configuration", incomplete.stderr)

        def login():
            entry = http.json("auth/login", "POST", {"username": "synthetic-recovery", "password": self.password})
            self.assertEqual(entry["user"], seed["account"])

        def history():
            entries = http.json("watch/sessions/" + seed["session"] + "/coaching")["history"]
            self.assertEqual(entries[0]["coaching"], seed["text"])

        def assert_official_apk():
            status, headers, apk = http.request("/downloads/daljam-android.apk")
            self.assertEqual((status, len(apk), sha256(apk).hexdigest()), (200, 9_714_838, APK_SHA))
            self.assertIn("attachment", headers["content-disposition"])

        @contextmanager
        def container(image, label):
            name = tag + "-" + label
            docker("run", "-d", "--name", name, *args, image, check=True, stdout=subprocess.DEVNULL)
            try:
                yield name
            except (Exception, KeyboardInterrupt):
                docker("logs", name)
                raise
            finally:
                docker("rm", "-f", name, stdout=subprocess.DEVNULL)

        with container(candidate, "primary") as primary:
            http.ready()
            http.json("health")
            self.assertEqual(self.apply(database), ())
            login()
            history()
            http.json("auth/personalization", "POST", PROFILE)
            day = http.json("plans")["next_date"]
            http.json("plans/" + day, "POST", {"activities": [ACTIVITY]})
            assert_official_apk()
            docker("stop", "--time", "25", primary, check=True, stdout=subprocess.DEVNULL)
            stopped = docker("inspect", "--format={{.State.ExitCode}}", primary, check=True, capture_output=True)
            self.assertEqual(stopped.stdout.strip(), b"0", "Expected graceful SIGTERM, before Docker's timeout")
            logs = docker("logs", primary, check=True, capture_output=True)
            self.assertIn(b"Application shutdown complete.", logs.stderr + logs.stdout)
            docker("start", primary, check=True, stdout=subprocess.DEVNULL)
            http.ready()
            self.assertTrue(http.json("auth/personalization")["personalization"]["completed_at"])
            plans = http.json("plans")
            saved = next(plan for plan in (plans["today_plan"], plans["next_plan"]) if plan and plan["date"] == day)
            self.assertEqual(saved["activities"][0]["id"], ACTIVITY["id"])
            history()

        rejected = docker("run", "--rm", *args, "--env", "DALJAM_BACKUP_POLICY=render-pitr-7d-v1",
                          previous, capture_output=True)
        self.assertEqual(rejected.returncode, 1)
        self.assertIn(b"migration verification failed", rejected.stderr)
        before = self.snapshot(database, upgraded=True)
        with container(compatible, "rollback"):
            http.ready()
            login()
            history()
            assert_official_apk()
            http.json("alarms", "POST", {"bedtime": "23:15", "wake_time": "07:00",
                                      "timezone": "Asia/Seoul", "enabled": False})
        self.assertEqual(self.snapshot(database, upgraded=True), before)

        # Save only tested source-built images, never containers or DB volumes.
        if artifact_path := os.getenv('DALJAM_RELEASE_ARTIFACT_DIR'):
            destination = Path(artifact_path).resolve()
            self.assertTrue(destination.is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()))
            destination.mkdir(parents=True, exist_ok=False)
            commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            manifest = {'commit': commit, 'legacy_commit': LEGACY, 'rollback_source_commit': ROLLBACK_SOURCE,
                        'backup_policy': 'render-pitr-3d-v1',
                        'rollback_catalog_commit': commit,
                        'apk_sha256': APK_SHA, 'images': {}, 'contains_database': False}
            tags = []
            for role, image in (('candidate', candidate), ('rollback', compatible)):
                image_tag = f'daljam-release-{role}:{commit}'
                subprocess.run(['docker', 'tag', image, image_tag], check=True, timeout=30)
                image_id = subprocess.check_output(['docker', 'inspect', '--format={{.Id}}', image_tag], text=True).strip()
                manifest['images'][role] = {'tag': image_tag, 'id': image_id}
                tags.append(image_tag)
            raw = destination / 'images.tar'
            subprocess.run(['docker', 'save', '-o', str(raw), *tags], check=True, timeout=180)
            archive = destination / 'images.tar.gz'
            with raw.open('rb') as source, gzip.open(archive, 'wb', compresslevel=1) as output:
                shutil.copyfileobj(source, output)
            raw.unlink()  # Only this newly generated duplicate archive; no database files.
            with archive.open('rb') as source:
                from hashlib import file_digest
                manifest['archive_sha256'] = file_digest(source, 'sha256').hexdigest()
            manifest['archive_bytes'] = archive.stat().st_size
            (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
