"""Windows executable entrypoint for MSFI monitor (LAN-first)."""

from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from app import create_app


APP_NAME = "MSFI_Monitor"
DEFAULT_PORT = 5000


def _resource_base() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def _template_folder() -> Path:
    return _resource_base() / "templates"


def _data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _detect_lan_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        except OSError:
            return "127.0.0.1"


def _open_browser_async(url: str) -> None:
    timer = threading.Timer(1.2, lambda: webbrowser.open(url))
    timer.daemon = True
    timer.start()


def main() -> None:
    port = int(os.environ.get("MSFI_PORT", str(DEFAULT_PORT)))
    db_path = _data_dir() / "msfi.db"
    app = create_app(
        test_config={"DATABASE": str(db_path)},
        template_folder=str(_template_folder()),
    )

    lan_ip = _detect_lan_ip()
    host = "0.0.0.0"
    browser_url = f"http://{lan_ip}:{port}"
    print(f"MSFI running with LAN access on {host}:{port}")
    print(f"Open on this PC: http://127.0.0.1:{port}")
    print(f"Open on LAN: {browser_url}")
    _open_browser_async(browser_url)
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
