"""Runner checks. Set DALJAM_TEST_POSTGRES_BIN to run the real-engine tests.

The opt-in suite starts its own temporary cluster. Existing DATABASE_URL values
are never used as a test target. DALJAM_TEST_OPENSSL can point to openssl.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch

import postgres_migrate as runner
import postgres_db
from test_postgres_schema import source_schema, table_names


def copy_migrations(test):
    directory = Path(test.enterContext(tempfile.TemporaryDirectory()))
    shutil.copytree(runner.MIGRATIONS, directory, dirs_exist_ok=True)
    return directory


def write_manifest(directory, manifest):
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def manifest_at(directory):
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def write_version(directory, version, text):
    manifest = manifest_at(directory)
    file = "0001_initial_schema.sql" if version == 1 else f"{version:04d}_test_schema.sql"
    (directory / file).write_text(text, encoding="utf-8", newline="\n")
    entry = {"version": version, "file": file, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    if version == 1:
        manifest["migrations"][0].update(entry)
    else:
        manifest["migrations"].append(entry)
    write_manifest(directory, manifest)


class MigrationManifestTests(unittest.TestCase):
    def test_crlf_checkout_keeps_the_same_checksum(self):
        directory = copy_migrations(self)
        file = directory / "0001_initial_schema.sql"
        original = runner.load_migrations()
        file.write_bytes(file.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(runner.load_migrations(directory), original)

    def test_file_checksum_mismatch_fails_before_connection(self):
        directory = copy_migrations(self)
        file = directory / "0001_initial_schema.sql"
        with file.open("a", encoding="utf-8") as stream:
            stream.write("\n-- changed")
        with patch.object(postgres_db, "connect_postgres") as connect:
            with self.assertRaisesRegex(runner.MigrationManifestError, "체크섬"):
                runner.apply_migrations(directory)
        connect.assert_not_called()

    def test_out_of_order_manifest_fails_before_connection(self):
        directory = copy_migrations(self)
        write_version(directory, 2, "SELECT 1;")
        manifest = manifest_at(directory)
        manifest["migrations"].reverse()
        write_manifest(directory, manifest)
        with patch.object(postgres_db, "connect_postgres") as connect:
            with self.assertRaisesRegex(runner.MigrationManifestError, "순서"):
                runner.apply_migrations(directory)
        connect.assert_not_called()

    def test_relative_path_is_not_a_migration_filename(self):
        directory = copy_migrations(self)
        manifest = manifest_at(directory)
        manifest["migrations"][0]["file"] = "../0001_initial_schema.sql"
        write_manifest(directory, manifest)
        with self.assertRaisesRegex(runner.MigrationManifestError, "파일 이름"):
            runner.load_migrations(directory)

    def test_cli_configuration_error_does_not_print_url(self):
        synthetic = "invalid-synthetic-url"
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"DATABASE_URL": synthetic}), redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(runner.main(), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("DATABASE_URL", errors.getvalue())
        self.assertNotIn(synthetic, errors.getvalue())


@unittest.skipUnless(os.getenv("DALJAM_TEST_POSTGRES_BIN"), "Set DALJAM_TEST_POSTGRES_BIN for local PostgreSQL")
class MigrationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from postgres_migration_fixture import PostgresTestCluster

        cls.enterClassContext(patch.dict(os.environ))
        for name in list(os.environ):
            if name == "DATABASE_URL" or name.startswith("PG"):
                del os.environ[name]
        cls.cluster = PostgresTestCluster(cls, Path(os.environ["DALJAM_TEST_POSTGRES_BIN"]))

    def setUp(self):
        self.database = self.cluster.new_database()
        self.enterContext(patch.dict(os.environ, {"DATABASE_URL": self.cluster.url(self.database)}))

    def public_tables(self, connection):
        return {row["tablename"] for row in connection.execute(
            "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'"
        )}

    def test_initial_schema_keys_indexes_and_idempotency(self):
        with closing(source_schema()) as source:
            expected = table_names(source)
        self.assertEqual(len(expected), 20)
        self.assertEqual(runner.apply_migrations(), (1,))
        self.assertEqual(runner.apply_migrations(), ())
        with self.cluster.connect(self.database) as connection:
            self.assertTrue(connection.info.pgconn.ssl_in_use)
            self.assertEqual(self.public_tables(connection), expected | {"daljam_schema_migrations"})
            rows = connection.execute(
                "SELECT contype, count(*) AS total FROM pg_catalog.pg_constraint "
                "WHERE connamespace = 'public'::regnamespace "
                "AND conrelid <> 'public.daljam_schema_migrations'::regclass "
                "AND contype IN ('p','f','u') GROUP BY contype"
            )
            self.assertEqual({row["contype"]: row["total"] for row in rows}, {"p": 19, "f": 17, "u": 3})
            indexes = {row["indexname"] for row in connection.execute(
                "SELECT indexname FROM pg_catalog.pg_indexes WHERE schemaname = 'public'"
            )}
            self.assertTrue({
                "sessions_subject_start", "samples_observation", "coaching_account_session",
                "trash_sessions_owner_time", "trash_coaching_owner_time", "coaching_requests_time",
            } <= indexes)
            row, = connection.execute(
                "SELECT version, name, sha256, applied_at FROM public.daljam_schema_migrations"
            ).fetchall()
            first, = runner.load_migrations()
            self.assertEqual((row["version"], row["name"], row["sha256"]), (1, first.name, first.sha256))
            self.assertIsNotNone(row["applied_at"])

    def test_saved_checksum_detects_changed_sql_even_with_updated_manifest(self):
        runner.apply_migrations()
        directory = copy_migrations(self)
        original = (directory / "0001_initial_schema.sql").read_text(encoding="utf-8")
        write_version(directory, 1, original.replace("COMMIT;", "-- changed after apply\nCOMMIT;"))
        with self.assertRaisesRegex(runner.MigrationHistoryError, "DB 이력 체크섬"):
            runner.apply_migrations(directory)
        self.assertEqual(runner.apply_migrations(), ())

    def test_legacy_history_cannot_be_silently_adopted(self):
        original = (runner.MIGRATIONS / "0001_initial_schema.sql").read_text(encoding="utf-8")
        with self.cluster.connect(self.database) as connection:
            connection.execute(original)
        with self.assertRaisesRegex(runner.MigrationHistoryError, "필수 열"):
            runner.apply_migrations()
        with self.cluster.connect(self.database) as connection:
            self.assertEqual(len(self.public_tables(connection)), 21)
            columns = connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'daljam_schema_migrations'"
            )
            self.assertNotIn("sha256", {row["column_name"] for row in columns})

    def test_failed_initial_migration_rolls_back_all_tables_and_history(self):
        directory = copy_migrations(self)
        original = (directory / "0001_initial_schema.sql").read_text(encoding="utf-8")
        write_version(directory, 1, original.replace("COMMIT;", "CREATE TABLE public.accounts (bad INT);\nCOMMIT;"))
        with self.assertRaisesRegex(runner.MigrationError, "버전 1 적용"):
            runner.apply_migrations(directory)
        with self.cluster.connect(self.database) as connection:
            self.assertEqual(self.public_tables(connection), set())
        self.assertEqual(runner.apply_migrations(), (1,))

    def test_followup_is_recorded_and_migration_cannot_commit_early(self):
        self.assertEqual(runner.apply_migrations(), (1,))
        directory = copy_migrations(self)
        write_version(directory, 2, "CREATE TABLE public.synthetic_extra (id BIGINT PRIMARY KEY);")
        write_version(directory, 3, "CREATE TABLE public.synthetic_partial (id BIGINT); COMMIT;")
        with self.assertRaisesRegex(runner.MigrationError, "버전 3 적용"):
            runner.apply_migrations(directory)
        with self.cluster.connect(self.database) as connection:
            self.assertNotIn("synthetic_extra", self.public_tables(connection))
            self.assertNotIn("synthetic_partial", self.public_tables(connection))
            rows = connection.execute("SELECT version FROM public.daljam_schema_migrations").fetchall()
            self.assertEqual(rows, [{"version": 1}])
        manifest = manifest_at(directory)
        manifest["migrations"].pop()
        write_manifest(directory, manifest)
        self.assertEqual(runner.apply_migrations(directory), (2,))
        self.assertEqual(runner.apply_migrations(directory), ())

    def test_concurrent_runner_waits_and_applies_initial_schema_once(self):
        applying, release = Event(), Event()
        original = runner._apply_one

        def pause_first(connection, migration):
            applying.set()
            if not release.wait(timeout=5):
                raise AssertionError("Timed out waiting to release the first migrator")
            original(connection, migration)

        with patch.object(runner, "_apply_one", side_effect=pause_first) as apply:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(runner.apply_migrations)
                try:
                    self.assertTrue(applying.wait(timeout=3))
                    second = pool.submit(runner.apply_migrations)
                    with self.cluster.connect(self.database) as observer:
                        deadline = time.monotonic() + 3
                        while time.monotonic() < deadline:
                            waiting = observer.execute(
                                "SELECT 1 FROM pg_catalog.pg_locks WHERE locktype = 'advisory' AND NOT granted "
                                "AND database = (SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database())"
                            ).fetchone()
                            if waiting:
                                break
                            time.sleep(0.025)
                        self.assertIsNotNone(waiting, "The second migrator did not wait on the database lock")
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=8), (1,))
                self.assertEqual(second.result(timeout=8), ())
            apply.assert_called_once()

    def test_connection_refused_has_safe_error(self):
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
            with patch.dict(os.environ, {"DATABASE_URL": self.cluster.url(self.database, port=port)}):
                with self.assertRaises(postgres_db.PostgresConnectionError) as error:
                    runner.apply_migrations(connect_timeout=2)
        self.assertNotIn(self.cluster.password, str(error.exception))
        self.assertIsNone(error.exception.__cause__)

    def test_disconnection_before_commit_leaves_no_schema(self):
        original = runner._apply_one

        def disconnect(connection, migration):
            original(connection, migration)
            with self.cluster.connect() as observer:
                terminated = observer.execute(
                    "SELECT pg_catalog.pg_terminate_backend(%s, 2000) AS stopped",
                    (connection.info.backend_pid,),
                ).fetchone()
                self.assertTrue(terminated["stopped"])

        with patch.object(runner, "_apply_one", side_effect=disconnect):
            with self.assertRaisesRegex(postgres_db.PostgresConnectionError, "연결이 끊겼습니다"):
                runner.apply_migrations()
        with self.cluster.connect(self.database) as connection:
            self.assertEqual(self.public_tables(connection), set())
        self.assertEqual(runner.apply_migrations(), (1,))
