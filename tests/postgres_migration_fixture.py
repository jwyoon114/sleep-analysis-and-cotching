"""A disposable, TLS-only loopback PostgreSQL cluster for migration tests."""

from pathlib import Path
import os
import secrets
import shutil
import socket
import subprocess
from tempfile import mkdtemp, gettempdir

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


class PostgresTestCluster:
    def __init__(self, test_case, bin_dir: Path):
        self.bin_dir = bin_dir.resolve()
        self.root = Path(mkdtemp(prefix="daljam-pg-migration-")).resolve()
        self.data = self.root / "cluster"
        test_case.addClassCleanup(self.cleanup)
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
                     "--encoding=UTF8", "--no-locale", "--no-sync", "--auth=scram-sha-256",
                     "--pwfile=" + str(pwfile))
        finally:
            pwfile.unlink(missing_ok=True)

        openssl = os.environ.get("DALJAM_TEST_OPENSSL") or shutil.which("openssl")
        config = self.root / "openssl.cnf"
        config.write_text("[req]\ndistinguished_name=dn\n[dn]\nCN=localhost\n", encoding="ascii")
        if openssl:
            self.command(openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                         "-config", str(config), "-subj", "/CN=localhost",
                         "-keyout", str(self.data / "server.key"), "-out", str(self.data / "server.crt"))
        else:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import NameOID
            from datetime import datetime, timedelta, timezone
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
            now = datetime.now(timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
                    .sign(key, hashes.SHA256()))
            (self.data / 'server.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
            (self.data / 'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (self.data / "server.key").chmod(0o600)
        with (self.data / "postgresql.conf").open("a", encoding="ascii") as file:
            file.write(f"\nlisten_addresses = '127.0.0.1'\nport = {self.port}\nssl = on\n")
            # Disposable test cluster only: exercise SQL/transactions, not
            # physical crash durability or production backup recovery.
            file.write("fsync = off\nsynchronous_commit = off\nfull_page_writes = off\n")
        (self.data / "pg_hba.conf").write_text("hostssl all all 127.0.0.1/32 scram-sha-256\n", encoding="ascii")
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
            try:
                self.run("pg_ctl", "-D", str(self.data), "-m", "fast", "-t", "30", "-w", "stop")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                self.run("pg_ctl", "-D", str(self.data), "-m", "immediate", "-t", "30", "-w", "stop")

    def cleanup(self):
        # Never remove live database files, even when shutdown failed.
        self.stop()
        root = self.root.resolve()
        if root.parent != Path(gettempdir()).resolve() or not root.name.startswith('daljam-pg-migration-'):
            raise RuntimeError('Refusing cleanup outside the disposable test folder')
        if (self.data / 'postmaster.pid').exists():
            raise RuntimeError('Test cluster is still running; files were preserved')
        shutil.rmtree(root)

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
