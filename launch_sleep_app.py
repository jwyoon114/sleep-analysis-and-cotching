"""Windows desktop launcher. Install beside app.py; no third-party imports."""
import argparse
import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
STATE = ROOT / ".sleep_app_process.json"
LOCK = ROOT / ".sleep_app_launcher.lock"
LOG = ROOT / "sleep_app_launcher.log"
PORT = 8511
URL = f"http://127.0.0.1:{PORT}"

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.GetProcessTimes.argtypes = (
    wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
)
kernel.GetProcessTimes.restype = wintypes.BOOL
kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel.CloseHandle.restype = wintypes.BOOL
kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
kernel.TerminateProcess.restype = wintypes.BOOL


def signature(handle):
    created, ended, system, user = (wintypes.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(
        handle, ctypes.byref(created), ctypes.byref(ended),
        ctypes.byref(system), ctypes.byref(user),
    ):
        return None
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


def process_signature(pid):
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return None
    try:
        return signature(handle)
    finally:
        kernel.CloseHandle(handle)


def read_state():
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if data.get("root") != str(ROOT) or data.get("port") != PORT:
            return None
        if process_signature(data["pid"]) != data["created"]:
            return None
        return data
    except (OSError, ValueError, TypeError, KeyError):
        return None


def ready():
    try:
        # Always connect directly to loopback, regardless of proxy settings.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL + "/_stcore/health", timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def stop():
    state = read_state()
    if state is None:
        return "실행 중인 전용 수면 앱이 없습니다."
    # Check creation time again on the same handle used for termination. This
    # prevents terminating an unrelated process if Windows has reused a PID.
    handle = kernel.OpenProcess(0x1000 | 0x0001, False, state["pid"])
    if not handle:
        return "앱이 이미 종료됐습니다."
    try:
        if signature(handle) != state["created"]:
            raise RuntimeError("프로세스 정보가 달라 종료하지 않았습니다.")
        if not kernel.TerminateProcess(handle, 0):
            raise OSError("수면 앱 프로세스를 종료하지 못했습니다.")
    finally:
        kernel.CloseHandle(handle)
    STATE.unlink(missing_ok=True)
    return "수면 앱을 종료했습니다. 브라우저 탭도 닫으셔도 됩니다."


def start(open_browser=True):
    state = read_state()
    if state is None:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", PORT)) == 0:
                raise RuntimeError(f"{PORT}번 포트를 다른 프로그램이 사용 중입니다.")
        if not PYTHON.is_file() or not (ROOT / "app.py").is_file():
            raise FileNotFoundError("프로젝트의 app.py와 .venv 실행 환경을 확인하세요.")
        # Launch Python itself instead of the virtualenv redirector, so the
        # recorded PID owns the server and stopping it cannot orphan a child.
        python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
        env = os.environ.copy()
        env.update({"PYTHONPATH": str(ROOT / ".venv" / "Lib" / "site-packages"),
                    "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1"})
        with LOG.open("ab") as output:
            process = subprocess.Popen(
                [python, "-m", "streamlit", "run", str(ROOT / "app.py"),
                 f"--server.port={PORT}", "--server.address=127.0.0.1",
                 "--server.fileWatcherType=none",
                 "--server.headless=true", "--browser.gatherUsageStats=false"],
                cwd=str(ROOT), stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        created = process_signature(process.pid)
        if created is None:
            raise RuntimeError(f"앱이 시작되지 않았습니다. {LOG.name}을 확인하세요.")
        state = {"pid": process.pid, "created": created, "root": str(ROOT), "port": PORT}
        STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process_signature(state["pid"]) != state["created"]:
            raise RuntimeError(f"실행 중 오류가 발생했습니다. {LOG.name}을 확인하세요.")
        if ready():
            if open_browser:
                webbrowser.open(URL, new=2)
            return f"수면 앱 실행 완료: {URL}"
        time.sleep(0.15)
    raise RuntimeError(f"앱 준비가 지연되고 있습니다. {LOG.name}을 확인하세요.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        with LOCK.open("a+b") as lock:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("앱을 시작하거나 종료하는 중입니다. 잠시 후 다시 실행하세요.")
            try:
                message = stop() if args.stop else start(not args.no_browser)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        if sys.stdout is not None:
            print(message)
    except Exception as error:
        if sys.stderr is not None:
            print(str(error), file=sys.stderr)
        if not args.quiet:
            ctypes.windll.user32.MessageBoxW(0, str(error), "수면 EEG 분석", 0x10)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
