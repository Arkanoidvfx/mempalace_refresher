from __future__ import annotations

import ctypes
import subprocess
from socket import create_connection
from random import randint
from threading import Event, Thread
from time import monotonic, sleep
from urllib.request import Request, urlopen

from .service import WatcherService
from .web import build_server
from .windows import hidden_subprocess_kwargs


def _wait_for_server(url: str, timeout_seconds: float = 15.0) -> None:
    deadline = monotonic() + timeout_seconds
    last_error: Exception | None = None
    while monotonic() < deadline:
        try:
            with urlopen(url, timeout=1):  # noqa: S310 - local loopback only
                return
        except Exception as exc:  # pragma: no cover - startup timing
            last_error = exc
            sleep(0.25)
    raise RuntimeError(f"Dashboard server did not become ready at {url}") from last_error


def _request_shutdown(url: str) -> None:
    try:
        req = Request(url, method="POST")
        with urlopen(req, timeout=2):  # noqa: S310 - local loopback only
            return
    except Exception:
        return


def _port_is_listening(host: str, port: int) -> bool:
    try:
        with create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _listener_pids(port: int) -> list[int]:
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except Exception:
        return []
    pids: set[int] = set()
    needle = f":{port}"
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if needle not in line or "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if not parts:
            continue
        pid_text = parts[-1]
        if pid_text.isdigit():
            pids.add(int(pid_text))
    return sorted(pids)


def _terminate_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                text=True,
                check=False,
                **hidden_subprocess_kwargs(),
            )
        except Exception:
            continue


def _release_dashboard_port(host: str, port: int) -> None:
    if not _port_is_listening(host, port):
        return
    _request_shutdown(f"http://{host}:{port}/api/actions/shutdown")
    deadline = monotonic() + 3.0
    while monotonic() < deadline:
        if not _port_is_listening(host, port):
            return
        sleep(0.25)
    _terminate_pids(_listener_pids(port))
    deadline = monotonic() + 3.0
    while monotonic() < deadline:
        if not _port_is_listening(host, port):
            return
        sleep(0.25)


def _set_taskbar_identity() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MemPalaceWatcher")
    except Exception:
        pass


def run_desktop(service: WatcherService) -> None:
    try:
        import webview
    except ImportError as exc:  # pragma: no cover - dependency issue
        raise RuntimeError(
            "pywebview is not installed in the project venv. Run .venv\\Scripts\\python.exe -m pip install pywebview"
        ) from exc

    host = service.config.server_host
    configured_port = service.config.server_port
    _release_dashboard_port(host, configured_port)
    _set_taskbar_identity()
    stop_event = Event()
    watcher_thread = Thread(target=service.run_loop, args=(stop_event,), daemon=True)
    watcher_thread.start()

    server = build_server(service, stop_event, port=0)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/?v={randint(100000, 999999)}"
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    _wait_for_server(url)
    shutdown_called = False

    def shutdown() -> None:
        nonlocal shutdown_called
        if shutdown_called:
            return
        shutdown_called = True
        stop_event.set()
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass

    window = webview.create_window(
        "MemPalace Watcher",
        url,
        width=1680,
        height=1024,
        min_size=(1280, 820),
        background_color="#020617",
        focus=False,
    )
    window.events.closed += shutdown
    try:
        icon_path = service.project_root / "icon.ico"
        webview.start(gui="edgechromium", debug=False, icon=str(icon_path) if icon_path.is_file() else None)
    finally:
        shutdown()
