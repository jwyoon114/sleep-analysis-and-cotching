"""Upgrade 0007 synthetic data; never connect to an existing DATABASE_URL."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import account_personalization
import coaching_service
import postgres_migrate
from postgres_migration_fixture import PostgresTestCluster


@unittest.skipUnless(os.getenv("DALJAM_TEST_POSTGRES_BIN"), "isolated PostgreSQL tools not selected")
class IndependentConsentMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = PostgresTestCluster(cls, Path(os.environ["DALJAM_TEST_POSTGRES_BIN"]))

    def test_upgrade_repeat_existing_text_and_other_constraints(self):
        database = self.cluster.new_database()
        self.enterContext(patch.dict(os.environ, {"SLEEP_DB_BACKEND": "postgresql", "DATABASE_URL": self.cluster.url(database)}))
        folder = Path(self.enterContext(TemporaryDirectory()))
        shutil.copytree(postgres_migrate.MIGRATIONS, folder, dirs_exist_ok=True)
        path = folder / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["migrations"] = manifest["migrations"][:7]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(postgres_migrate.apply_migrations(folder), tuple(range(1, 8)))
        with self.cluster.connect(database) as db:
            db.execute("INSERT INTO accounts VALUES('synthetic-owner','synthetic-owner','hash','salt','2024-11-01')")
            db.execute("INSERT INTO account_personalization VALUES('synthetic-owner','ISTJ','casual','direct',TRUE,'cat','2024-11-01')")
            db.execute("INSERT INTO sessions VALUES('synthetic-record','synthetic-owner','2024-11-15','2024-11-16','{}')")
            db.execute("INSERT INTO coaching VALUES('synthetic-old','synthetic-owner','synthetic-record','과거 조언 원문.','{}','2024-11-16')")
            db.execute("INSERT INTO coaching_preferences VALUES('synthetic-owner','성인','23:30','07:00')")
            db.execute("INSERT INTO coaching_daily_habits VALUES('synthetic-owner','2024-11-15','있음','보통')")
            self.assertEqual(db.execute("SELECT count(*) AS n FROM pg_constraint WHERE conname='account_personalization_check'").fetchone()["n"], 1)
        self.assertEqual(postgres_migrate.apply_migrations(), (8,))
        self.assertEqual(postgres_migrate.apply_migrations(), ())
        with self.cluster.connect(database) as db:
            migration = postgres_migrate.load_migrations()[-1]
            db.execute(migration.body)
            db.execute(migration.body)
            for intensity in ("gentle", "firm", "direct"):
                db.execute("UPDATE account_personalization SET intensity=%s, allow_profanity=TRUE", (intensity,))
                profile = account_personalization.get_personalization("synthetic-owner")
                self.assertTrue(profile["allow_profanity"])
                self.assertEqual(profile["intensity"], intensity)
            self.assertEqual(db.execute("SELECT text FROM coaching WHERE id='synthetic-old'").fetchone()["text"], "과거 조언 원문.")
            for table in ("accounts", "sessions", "coaching", "account_personalization", "coaching_preferences", "coaching_daily_habits"):
                self.assertEqual(db.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"], 1)
            import psycopg
            with self.assertRaises(psycopg.errors.CheckViolation):
                db.execute("UPDATE account_personalization SET speech='unsupported'")
            with self.assertRaises(postgres_migrate.MigrationHistoryError):
                postgres_migrate.inspect_history(db, postgres_migrate.load_migrations(folder))
