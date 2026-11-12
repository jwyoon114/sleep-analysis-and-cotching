"""Offline schema contract tests. Never import the API or contact PostgreSQL.

SQLite executes a restricted DDL translation to test relationships locally.
This is NOT a substitute for running the migration on PostgreSQL itself.
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "postgresql"
HISTORY = "daljam_schema_migrations"
TYPE_MAP = {"TEXT": "TEXT", "INTEGER": "BIGINT", "REAL": "DOUBLE PRECISION"}


def statements(sql):
    # This migration deliberately has no dollar quotes, procedural SQL or
    # semicolons in string literals. Reject every unrecognized statement.
    sql = re.sub(r"--[^\n]*", "", sql)
    result = [s.strip() for s in sql.split(";") if s.strip()]
    allowed = (
        r"BEGIN", r"COMMIT",
        r"SET LOCAL lock_timeout = '5s'",
        r"SET LOCAL statement_timeout = '60s'",
        r"SET LOCAL search_path = pg_catalog, public",
        r"CREATE TABLE public\.[a-z_]+ \(.+\)",
        r"CREATE INDEX [a-z_]+ ON public\.[a-z_]+ \(.+\)",
        r'INSERT INTO public\.daljam_schema_migrations \("version", "name"\)\s+'
        r"VALUES \(1, '0001_initial_schema'\)",
    )
    for statement in result:
        if not any(re.fullmatch(pattern, statement, flags=re.S) for pattern in allowed):
            raise ValueError("Unexpected migration statement")
    return result


def database():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    # UTF-8 byte ordering mirrors SQLite's default BINARY collation.
    db.create_collation("C", lambda a, b: (a.encode() > b.encode()) - (a.encode() < b.encode()))
    return db


def source_schema():
    """Evaluate only literal schema DDL from source, never service code/data."""
    db = database()
    try:
        for filename, function in (
            ("health_records.py", "connect"),
            ("health_sync.py", "database"),
            ("sleep_alarms.py", "connect"),
        ):
            module = ast.parse((ROOT / filename).read_text(encoding="utf-8-sig"))
            definition = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == function)
            calls = sorted((n for n in ast.walk(definition) if isinstance(n, ast.Call)), key=lambda n: n.lineno)
            for call in calls:
                if not isinstance(call.func, ast.Attribute) or call.func.attr not in {"execute", "executescript"} or not call.args:
                    continue
                argument = call.args[0]
                if (
                    isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                    and argument.value.lstrip().upper().startswith(("CREATE TABLE", "ALTER TABLE"))
                ):
                    db.executescript(argument.value)
        return db
    except BaseException:
        db.close()
        raise


def target_schema(sql):
    """Local logical model: remove only public qualification and SET LOCAL."""
    db = database()
    try:
        for statement in statements(sql):
            if statement.startswith(("CREATE TABLE ", "CREATE INDEX ")):
                db.execute(statement.replace("public.", ""))
        return db
    except BaseException:
        db.close()
        raise


def table_names(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def columns(db, table):
    return [dict(r) for r in db.execute('PRAGMA table_info("' + table + '")')]


def primary_key(db, table):
    return tuple(c["name"] for c in sorted(columns(db, table), key=lambda c: c["pk"]) if c["pk"])


def foreign_keys(db, table):
    return sorted(
        (r["from"], r["table"], r["to"], r["on_update"], r["on_delete"])
        for r in db.execute('PRAGMA foreign_key_list("' + table + '")')
    )


def indexes(db, table, origin):
    result = []
    for row in db.execute('PRAGMA index_list("' + table + '")'):
        if row["origin"] == origin:
            cols = tuple(r["name"] for r in db.execute('PRAGMA index_info("' + row["name"] + '")'))
            result.append((row["name"] if origin == "c" else "", row["unique"], cols))
    return sorted(result)


class PostgresSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((MIGRATIONS / "manifest.json").read_text(encoding="utf-8"))
        cls.entry = cls.manifest["migrations"][0]
        cls.sql = (MIGRATIONS / cls.entry["file"]).read_text(encoding="utf-8")

    def setUp(self):
        self.source = source_schema()
        self.addCleanup(self.source.close)
        self.target = target_schema(self.sql)
        self.addCleanup(self.target.close)

    def account(self, identifier="synthetic-account"):
        self.target.execute(
            "INSERT INTO accounts VALUES(?,?,?,?,?)",
            (identifier, identifier, "synthetic-hash", "synthetic-salt", "2026-01-01T00:00:00+00:00"),
        )
        return identifier

    def session(self, identifier="synthetic-session", subject="synthetic-account"):
        self.target.execute(
            "INSERT INTO sessions VALUES(?,?,?,?,?)",
            (identifier, subject, "2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", "{}"),
        )
        return identifier

    def test_manifest_pins_version_file_and_checksum(self):
        self.assertEqual(self.manifest["format_version"], 1)
        self.assertEqual(self.manifest["dialect"], "postgresql")
        self.assertEqual(self.manifest["schema"], "public")
        self.assertEqual(len(self.manifest["migrations"]), 1)
        self.assertEqual(self.entry["version"], 1)
        self.assertEqual(self.entry["file"], "0001_initial_schema.sql")
        self.assertEqual(self.entry["application_tables"], 20)
        canonical = self.sql.replace("\r\n", "\n").encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), self.entry["sha256"])

    def test_exact_twenty_application_tables_and_eighty_five_columns(self):
        self.assertEqual(len(table_names(self.source)), 20)
        self.assertEqual(table_names(self.target) - {HISTORY}, table_names(self.source))
        self.assertEqual(sum(len(columns(self.source, t)) for t in table_names(self.source)), 85)
        for table in table_names(self.source):
            with self.subTest(table=table):
                old, new = columns(self.source, table), columns(self.target, table)
                self.assertEqual([c["name"] for c in old], [c["name"] for c in new])
                for a, b in zip(old, new):
                    self.assertEqual(b["type"], TYPE_MAP[a["type"]])
                    self.assertEqual(b["dflt_value"], a["dflt_value"])
                    self.assertEqual(bool(b["notnull"]), bool(a["notnull"] or a["pk"]))

    def test_primary_keys_unique_constraints_and_six_indexes_match(self):
        counts = {"pk": 0, "u": 0, "c": 0}
        for table in table_names(self.source):
            with self.subTest(table=table):
                self.assertEqual(primary_key(self.target, table), primary_key(self.source, table))
                counts["pk"] += bool(primary_key(self.source, table))
                for origin in ("u", "c"):
                    self.assertEqual(indexes(self.target, table, origin), indexes(self.source, table, origin))
                    counts[origin] += len(indexes(self.source, table, origin))
        self.assertEqual(counts, {"pk": 19, "u": 3, "c": 6})
        # login_attempts intentionally has no PK or uniqueness constraint.
        self.assertEqual(primary_key(self.target, "login_attempts"), ())

    def test_all_seventeen_foreign_keys_and_five_cascades_match(self):
        count = cascades = 0
        for table in table_names(self.source):
            old, new = foreign_keys(self.source, table), foreign_keys(self.target, table)
            self.assertEqual(new, old, table)
            count += len(new)
            cascades += sum(f[-1] == "CASCADE" for f in new)
        self.assertEqual((count, cascades), (17, 5))
        self.assertEqual(self.sql.count("NOT DEFERRABLE"), 17)
        # No new ownership FK is invented for columns without one in SQLite.
        self.assertEqual(foreign_keys(self.target, "sessions"), [])
        self.assertEqual(foreign_keys(self.target, "coaching_requests"), [])

    def test_expected_pk_null_tightening_is_explicit(self):
        tightened = {
            (t, c["name"]) for t in table_names(self.source)
            for c in columns(self.source, t) if c["pk"] and not c["notnull"]
        }
        self.assertEqual(len(tightened), 17)
        for table, column in tightened:
            self.assertTrue(next(c for c in columns(self.target, table) if c["name"] == column)["notnull"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.target.execute("INSERT INTO accounts VALUES(NULL,'synthetic','hash','salt','time')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.target.execute("INSERT INTO import_sessions VALUES(NULL,NULL)")

    def test_health_connections_includes_latest_column_and_default(self):
        actual = {c["name"]: c for c in columns(self.target, "health_connections")}
        self.assertIn("last_window_end", actual)
        self.assertFalse(actual["last_window_end"]["notnull"])
        self.assertFalse(actual["last_synced_at"]["notnull"])
        self.assertEqual(actual["auto_coach"]["dflt_value"], "0")
        self.assertEqual(actual["auto_coach"]["type"], "BIGINT")

    def test_parent_tables_precede_foreign_keys_and_names_fit_postgres(self):
        created = set()
        for statement in statements(self.sql):
            if statement.startswith("CREATE TABLE "):
                name = re.match(r"CREATE TABLE public\.([a-z_]+)", statement).group(1)
                for parent in re.findall(r"REFERENCES public\.([a-z_]+)", statement):
                    self.assertIn(parent, created)
                created.add(name)
        names = re.findall(r"(?:CONSTRAINT|CREATE INDEX) ([a-z_]+)", self.sql)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(len(n.encode("utf-8")) <= 63 for n in names))

    def test_transaction_metadata_and_safe_statement_set(self):
        parts = statements(self.sql)
        self.assertEqual(parts[0], "BEGIN")
        self.assertEqual(parts[-1], "COMMIT")
        self.assertEqual(sum(s == "BEGIN" for s in parts), 1)
        self.assertEqual(sum(s == "COMMIT" for s in parts), 1)
        self.assertEqual(sum(s.startswith("CREATE TABLE ") for s in parts), 21)
        self.assertEqual(sum(s.startswith("CREATE INDEX ") for s in parts), 6)
        inserts = [s for s in parts if s.startswith("INSERT ")]
        self.assertEqual(len(inserts), 1)
        self.target.execute(inserts[0].replace("public.", ""))
        row = self.target.execute("SELECT version,name FROM " + HISTORY).fetchone()
        self.assertEqual(tuple(row), (1, "0001_initial_schema"))
        self.assertNotIn("IF NOT EXISTS", self.sql)
        self.assertNotIn("DATABASE_URL", self.sql)
        for addition in ("DROP TABLE accounts;", "SELECT 1;", "DELETE FROM sessions;"):
            with self.subTest(command=addition.split()[0]):
                with self.assertRaises(ValueError):
                    statements(self.sql + addition)

    def test_reapplying_schema_fails_without_silently_adopting_objects(self):
        first = next(s for s in statements(self.sql) if s.startswith("CREATE TABLE "))
        with self.assertRaises(sqlite3.OperationalError):
            self.target.execute(first.replace("public.", ""))
        self.assertEqual(len(table_names(self.target)), 21)

    def test_text_collation_and_numeric_width_are_preserved(self):
        text_count = sum(c["type"] == "TEXT" for t in table_names(self.source) for c in columns(self.source, t))
        self.assertEqual(self.sql.count('TEXT COLLATE "C"'), text_count + 1)  # history.name
        account = self.account()
        session = self.session(subject=account)
        self.target.execute(
            "INSERT INTO stages VALUES(?,?,?,?,?,?)",
            (session, 2**40, None, None, None, 0.123456789012345),
        )
        row = self.target.execute("SELECT position,minutes FROM stages").fetchone()
        self.assertEqual(row[0], 2**40)
        self.assertEqual(row[1], 0.123456789012345)

    def test_health_cascades_keep_unrelated_session_history(self):
        account, session = self.account(), self.session()
        self.target.execute(
            "INSERT INTO health_connections(account_id,token_hash,provider,source_id,source_name,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
            (account, "synthetic-token-hash", "healthkit", "synthetic-source", "synthetic-name", "time", "time"),
        )
        self.target.execute("INSERT INTO health_sync_sessions VALUES(?,?,?)", (account, "2026-01-01", session))
        self.target.execute("INSERT INTO health_advice_jobs VALUES(?,?)", (account, session))
        self.target.execute("DELETE FROM accounts WHERE id=?", (account,))
        for table in ("health_connections", "health_sync_sessions", "health_advice_jobs"):
            self.assertEqual(self.target.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)
        self.assertEqual(self.target.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)

    def test_session_cascades_and_no_action_auth_constraint(self):
        account, session = self.account(), self.session()
        self.target.execute("INSERT INTO health_sync_sessions VALUES(?,?,?)", (account, "2026-01-01", session))
        self.target.execute("INSERT INTO health_advice_jobs VALUES(?,?)", (account, session))
        self.target.execute("DELETE FROM sessions WHERE id=?", (session,))
        for table in ("health_sync_sessions", "health_advice_jobs"):
            self.assertEqual(self.target.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)
        self.target.execute("INSERT INTO auth_tokens VALUES(?,?,?)", ("synthetic-hash", account, "time"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.target.execute("DELETE FROM accounts WHERE id=?", (account,))
        self.assertEqual(self.target.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 1)

    def test_duplicate_day_and_session_links_are_rejected(self):
        a, b = self.account("synthetic-a"), self.account("synthetic-b")
        s1, s2 = self.session("synthetic-s1", a), self.session("synthetic-s2", a)
        self.target.execute("INSERT INTO health_sync_sessions VALUES(?,?,?)", (a, "2026-01-01", s1))
        for values in ((a, "2026-01-01", s2), (b, "2026-01-02", s1)):
            with self.subTest(collision=values[0]):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.target.execute("INSERT INTO health_sync_sessions VALUES(?,?,?)", values)

    @unittest.skipUnless(importlib.util.find_spec("pglast"), "Optional PostgreSQL parser is unavailable; no server validation")
    def test_optional_postgres_grammar_parser(self):
        from pglast import parse_sql
        self.assertEqual(len(parse_sql(self.sql)), len(statements(self.sql)))


if __name__ == "__main__":
    unittest.main()
