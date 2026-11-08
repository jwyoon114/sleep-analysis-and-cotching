"""Windows desktop entry for the Next.js UI and the existing Python backend."""
import argparse
import ctypes
import json
import msvcrt
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from launch_sleep_app import process_signature, kernel, signature

STATE = ROOT / ".runtime" / "web-processes.json"
URL = "http://127.0.0.1:3000"


def alive(item):
    return isinstance(item, dict) and process_signature(item["pid"]) == item["created"]


def healthy(url):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def free(port):
    with socket.socket() as connection:
        return connection.connect_ex(("127.0.0.1", port)) != 0


def stop():
    if not STATE.exists(): return
    data = json.loads(STATE.read_text(encoding="utf-8"))
    if data.get("root") != str(ROOT): raise RuntimeError("Launcher state mismatch.")
    for item in reversed(data.get("processes", [])):
        if not alive(item): continue
        handle = kernel.OpenProcess(0x1000 | 0x0001, False, item["pid"])
        if not handle: continue
        try:
            if signature(handle) == item["created"]:
                if not kernel.TerminateProcess(handle, 0): raise OSError("Could not stop the web app.")
        finally: kernel.CloseHandle(handle)
    STATE.unlink(missing_ok=True)


def start(project, open_browser=True):
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if state.get("root") == str(ROOT) and state.get("processes") and all(alive(p) for p in state["processes"]) and healthy(URL):
            if open_browser: webbrowser.open(URL)
            return
        stop()
    project = project.resolve(strict=True)
    if not (project / "api.py").is_file() or not (project / ".venv/Lib/site-packages").is_dir():
        raise RuntimeError("Choose the existing app folder containing api.py and .venv.")
    if not (ROOT / ".next/BUILD_ID").is_file():
        raise RuntimeError("Build the frontend first: npm install, then npm run build.")
    node = shutil.which("node.exe") or str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
    if not Path(node).is_file(): raise RuntimeError("Node.js is required.")
    if not free(3000): raise RuntimeError("Port 3000 is already in use. Close the development preview first.")
    state = {"root": str(ROOT), "processes": []}
    STATE.parent.mkdir(exist_ok=True)
    def spawn(args, cwd, env, name):
        with open(STATE.parent / (name + ".log"), "ab") as log:
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        created = process_signature(process.pid)
        if created is None: raise RuntimeError("Could not start " + name)
        state["processes"].append({"pid":process.pid,"created":created})
        STATE.write_text(json.dumps(state), encoding="utf-8")
    try:
        if free(8011):
            env = os.environ.copy()
            env.update({"SLEEP_DB_PATH": str(project / "data/sleep_records.sqlite3"), "PYTHONPATH": str(project / ".venv/Lib/site-packages"),
                        "PYTHONNOUSERSITE":"1", "PYTHONUTF8":"1", "COACHING_USER_LIMIT_24H":"10", "COACHING_GLOBAL_LIMIT_24H":"100"})
            spawn([str(Path(getattr(sys,"_base_executable",sys.executable)).resolve()), "-B", "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8011"], project, env, "api")
        elif not healthy("http://127.0.0.1:8011/health"):
            raise RuntimeError("Port 8011 is in use by an unavailable service.")
        env = os.environ.copy()
        env.update({"SLEEP_API_URL":"http://127.0.0.1:8011", "NEXT_TELEMETRY_DISABLED":"1"})
        spawn([node, str(ROOT / "node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1", "--port", "3000"], ROOT, env, "web")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if not all(alive(p) for p in state["processes"]): raise RuntimeError("A server stopped. Check sleep_frontend/.runtime logs.")
            if healthy(URL) and healthy("http://127.0.0.1:8011/health"):
                if open_browser: webbrowser.open(URL)
                return
            time.sleep(.3)
        raise RuntimeError("The app did not become ready. Check .runtime logs.")
    except BaseException:
        stop()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-project", type=Path)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        STATE.parent.mkdir(exist_ok=True)
        with (STATE.parent / "launcher.lock").open("a+b") as lock:
            lock.seek(0,2)
            if lock.tell()==0: lock.write(b"0"); lock.flush()
            lock.seek(0)
            try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError: raise RuntimeError("The app is starting or stopping. Please try again shortly.")
            try:
                if args.stop: stop()
                elif args.backend_project: start(args.backend_project, not args.no_browser)
                else: parser.error("--backend-project is required")
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(0, str(error), "달잠 웹앱", 0x10)
        raise SystemExit(1)
