"""Free, explicitly started HTTPS sharing for the existing Windows sleep app."""
import argparse
from contextlib import closing
import ctypes
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from launch_sleep_app import kernel, process_signature, signature

VERSION = "2026.10.7"
SHA256 = "2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343"
PORT = 8512
PUBLIC_PATTERN = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com")


def public_url(value):
    return isinstance(value, str) and PUBLIC_PATTERN.fullmatch(value) is not None


def terminate_owned(record):
    """Check process creation time on the handle we actually terminate."""
    if not isinstance(record, dict):
        return
    pid, created = record.get("pid"), record.get("created")
    if not isinstance(pid, int) or not isinstance(created, int):
        return
    handle = kernel.OpenProcess(0x1000 | 0x0001, False, pid)
    if not handle:
        return
    try:
        if signature(handle) != created:
            return
        if not kernel.TerminateProcess(handle, 0):
            raise OSError("공유용 프로세스를 종료하지 못했습니다.")
    finally:
        kernel.CloseHandle(handle)


def alive(record):
    return bool(isinstance(record, dict) and isinstance(record.get("pid"), int)
                and isinstance(record.get("created"), int)
                and process_signature(record["pid"]) == record["created"])


def reachable(url, timeout=5):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "/_stcore/health", timeout=timeout) as response:
            return response.status == 200 and response.read(16).strip() == b"ok"
    except (OSError, urllib.error.URLError):
        return False


class ShareApp:
    def __init__(self, project):
        self.root = Path(project).resolve()
        self.directory = self.root / ".sleep-share"
        self.state_path = self.directory / "state.json"
        self.tunnel_log = self.directory / "tunnel.log"
        self.server_log = self.directory / "server.log"
        self.local_url = f"http://127.0.0.1:{PORT}"

    def load(self):
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if state.get("project") == str(self.root) and state.get("port") == PORT:
                return state
        except (OSError, ValueError, TypeError):
            pass
        return None

    def save(self, state):
        temporary = self.directory / "state.new.json"
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.state_path)

    def spawn(self, command, log_path, env=None):
        with log_path.open("wb") as log:
            child = subprocess.Popen(command, cwd=self.root, env=env,
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        created = process_signature(child.pid)
        if created is None:
            child.terminate()
            raise RuntimeError("공유 프로세스를 시작하지 못했습니다.")
        return {"pid": child.pid, "created": created}

    def stop(self):
        state = self.load()
        if state:
            # Closing the public tunnel first immediately removes internet access.
            terminate_owned(state.get("tunnel"))
            terminate_owned(state.get("server"))
        self.state_path.unlink(missing_ok=True)
        (self.directory / "url.txt").unlink(missing_ok=True)
        return "인터넷 공유를 중지했습니다. 기존 PC 전용 앱은 계속 사용할 수 있습니다."

    def start(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        existing = self.load()
        if existing and alive(existing.get("tunnel")) and alive(existing.get("server")) and public_url(existing.get("url")) and reachable(self.local_url, 2) and reachable(existing["url"], 5):
            return existing["url"]
        if existing:
            self.stop()
        # Windows closes the listening socket shortly after TerminateProcess.
        # Wait only when we have just stopped our own recorded server.
        for _ in range(50 if existing else 1):
            with closing(socket.socket()) as sock:
                sock.settimeout(.2)
                if sock.connect_ex(("127.0.0.1", PORT)) != 0:
                    break
            time.sleep(.1)
        else:
            raise RuntimeError("8512번 포트를 다른 프로그램이 사용 중입니다. 기존 공유 상태를 확인하세요.")
        binary = self.directory / f"cloudflared-{VERSION}.exe"
        if not binary.is_file() or hashlib.sha256(binary.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError("검증된 Cloudflare 실행 파일이 없습니다. 공유 설치를 다시 실행하세요.")
        if not (self.root / "app.py").is_file():
            raise RuntimeError("현재 수면 앱의 app.py를 찾을 수 없습니다.")
        state = {"project": str(self.root), "port": PORT}
        try:
            # An explicit empty config keeps existing Cloudflare settings untouched.
            config = self.directory / "quick-tunnel.yml"
            config.write_text("{}\n", encoding="utf-8")
            state["tunnel"] = self.spawn([str(binary), "tunnel", "--config", str(config), "--no-autoupdate", "--edge-ip-version", "4", "--protocol", "http2", "--url", self.local_url], self.tunnel_log)
            self.save(state)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if not alive(state["tunnel"]):
                    raise RuntimeError("Cloudflare 연결이 종료됐습니다. 인터넷 연결과 tunnel.log를 확인하세요.")
                matches = PUBLIC_PATTERN.findall(self.tunnel_log.read_text(encoding="utf-8", errors="replace"))
                if matches:
                    state["url"] = matches[-1]
                    break
                time.sleep(.5)
            else:
                raise RuntimeError("무료 공유 주소 발급이 지연되고 있습니다. 잠시 후 다시 실행하세요.")
            env = os.environ.copy()
            env.update({"SLEEP_DB_PATH": str(self.root / "data" / "sleep_records.sqlite3"),
                        "COACHING_USER_LIMIT_24H": "10", "COACHING_GLOBAL_LIMIT_24H": "100",
                        "COACHING_MAX_INPUT_BYTES": "64000", "PYTHONUTF8": "1",
                        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                        "PYTHONPATH": str(self.root / ".venv" / "Lib" / "site-packages")})
            # Use the actual Python executable so stopping it also stops the server;
            # Windows virtualenv launchers otherwise leave a child Python running.
            python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
            hostname = urllib.parse.urlsplit(state["url"]).hostname
            state["server"] = self.spawn([python, "-B", "-m", "streamlit", "run", str(self.root / "app.py"),
                                           f"--server.port={PORT}", "--server.address=127.0.0.1",
                                           f"--browser.serverAddress={hostname}", "--browser.serverPort=443",
                                           "--server.enableCORS=true", "--server.enableXsrfProtection=true",
                                           "--server.enableStaticServing=false", "--server.maxUploadSize=10",
                                           "--server.headless=true", "--browser.gatherUsageStats=false",
                                           "--client.showErrorDetails=none"], self.server_log, env)
            self.save(state)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if not alive(state["server"]) or not alive(state["tunnel"]):
                    raise RuntimeError("공유 서버가 종료됐습니다. .sleep-share 폴더의 로그를 확인하세요.")
                if reachable(self.local_url, 2) and reachable(state["url"], 5):
                    (self.directory / "url.txt").write_text(state["url"], encoding="utf-8")
                    return state["url"]
                time.sleep(1)
            raise RuntimeError("외부 접속 확인 시간이 초과됐습니다. 인터넷 연결 후 다시 실행하세요.")
        except BaseException:
            # Record even a partially-started pair so cleanup cannot orphan it.
            self.save(state)
            self.stop()
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    app = ShareApp(args.project)
    app.directory.mkdir(parents=True, exist_ok=True)
    try:
        with (app.directory / "launcher.lock").open("a+b") as lock:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("공유를 시작하거나 중지하는 중입니다. 잠시 후 다시 실행하세요.") from None
            try:
                result = app.stop() if args.stop else app.start()
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        if sys.stdout is not None:
            print(result, flush=True)
        if not args.no_browser and not args.stop:
            webbrowser.open(result, new=2)
        if args.stop and not args.quiet:
            ctypes.windll.user32.MessageBoxW(0, result, "수면 앱 인터넷 공유", 0x40)
        return 0
    except Exception as error:
        if sys.stderr is not None:
            print(str(error), file=sys.stderr, flush=True)
        if not args.quiet:
            ctypes.windll.user32.MessageBoxW(0, str(error), "수면 앱 인터넷 공유", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
