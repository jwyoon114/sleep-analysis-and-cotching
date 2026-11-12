"""A disposable, TLS-only loopback PostgreSQL cluster for migration tests."""

from pathlib import Path
import os
import secrets
import shutil
import socket
import subprocess
from tempfile import TemporaryDirectory

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


class PostgresTestCluster:
    def __init__(self, test_case, bin_dir: Path):
        self.bin_dir = bin_dir.resolve()
        self.root = Path(test_case.enterClassContext(
            TemporaryDirectory(prefix="daljam-pg-migration-")
        )).resolve()
        self.data = self.root / "cluster"
        self.role = "daljam_test_admin"
        self.password = secrets.token_urlsafe(32)
        with socket.socket() as port:
            port.bind(("127.0.0.1", 0))
            self.port = port.getsockname()[1]

        pwfile = self.root / "initdb-password"
        fd = os.open(pwfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="ascii") as file:
                file.write(self.password + "\n")
            self.run("initdb", "-D", str(self.data), "--username=" + self.role,
                     "--encoding=UTF8", "--no-locale", "--auth=scram-sha-256",
                     "--pwfile=" + str(pwfile))
        finally:
            pwfile.unlink(missing_ok=True)

        openssl = os.environ.get("DALJAM_TEST_OPENSSL") or shutil.which("openssl")
        if not openssl:
            raise RuntimeError("Set DALJAM_TEST_OPENSSL or put openssl on PATH.")
        config = self.root / "openssl.cnf"
        config.write_text("[req]\ndistinguished_name=dn\n[dn]\nCN=localhost\n", encoding="ascii")
        self.command(openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                     "-config", str(config), "-subj", "/CN=localhost",
                     "-keyout", str(self.data / "server.key"), "-out", str(self.data / "server.crt"))
        (self.data / "server.key").chmod(0o600)
        with (self.data / "postgresql.conf").open("a", encoding="ascii") as file:
            file.write(f"\nlisten_addresses = '127.0.0.1'\nport = {self.port}\nssl = on\n")
        (self.data / "pg_hba.conf").write_text("hostssl all all 127.0.0.1/32 scram-sha-256\n", encoding="ascii")
        test_case.addClassCleanup(self.stop)
        self.run("pg_ctl", "-D", str(self.data), "-l", str(self.root / "postgres.log"), "-w", "start")

    @staticmethod
    def command(*args):
        # In particular, do not emit initdb output or test credentials.
        # On Windows pg_ctl can leave inherited pipe handles open in postgres.
        subprocess.run(
            args, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=65,
        )

    def run(self, name, *args):
        suffix = ".exe" if os.name == "nt" else ""
        self.command(str(self.bin_dir / (name + suffix)), *args)

    def stop(self):
        if (self.data / "postmaster.pid").is_file():
            self.run("pg_ctl", "-D", str(self.data), "-m", "fast", "-w", "stop")

    def url(self, name, *, port=None):
        return f"postgresql://{self.role}:{self.password}@127.0.0.1:{port or self.port}/{name}?sslmode=require"

    def connect(self, name="postgres", *, autocommit=True):
        return psycopg.connect(
            host="127.0.0.1", port=self.port, user=self.role, password=self.password,
            dbname=name, sslmode="require", connect_timeout=5, row_factory=dict_row, autocommit=autocommit,
        )

    def new_database(self):
        name = "daljam_test_" + secrets.token_hex(8)
        with self.connect() as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        return name
