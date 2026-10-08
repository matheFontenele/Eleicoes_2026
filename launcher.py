"""Local Windows-friendly controller for the packaged Streamlit dashboard.

Development: ``python launcher.py``. The frozen onedir executable re-executes
itself with ``--streamlit-child`` to host Streamlit without system Python/PATH.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:  # pragma: no cover - platform packaging diagnostic
    tk = None
    messagebox = None


APP_NAME = "CE2026Dashboard"
HEALTH_PATH = "/_stcore/health"
_CHILD_LOG_HANDLE = None


def resource_root() -> Path:
    """Project root when developing; PyInstaller onedir's _internal when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / APP_NAME


def free_loopback_port() -> int:
    """Ask the OS for an available local port (the server is bound to loopback)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def health_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}{HEALTH_PATH}"


def streamlit_args(port: int) -> list[str]:
    """Arguments passed directly to Click/Streamlit, without global sys.argv."""
    app = resource_root() / "dashboard.py"
    return [
        "run", str(app),
        "--server.address=127.0.0.1",
        f"--server.port={int(port)}",
        "--global.developmentMode=false",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
    ]


def run_streamlit_child(port: int) -> int:
    global _CHILD_LOG_HANDLE
    app = resource_root() / "dashboard.py"
    if not app.is_file():
        raise FileNotFoundError(f"Dashboard não encontrado no diretório de recursos: {app}")
    # Windowed PyInstaller builds may initialize sys.stdout/sys.stderr as None
    # even though the parent redirected the child process to its log file.
    if sys.stdout is None or sys.stderr is None:
        log_dir = user_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        _CHILD_LOG_HANDLE = (log_dir / "dashboard.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or _CHILD_LOG_HANDLE
        sys.stderr = sys.stderr or _CHILD_LOG_HANDLE
    from streamlit.web.cli import main as streamlit_main

    # Click's command object accepts explicit args. This avoids mutating argv,
    # which otherwise collides with the launcher's --streamlit-child options.
    streamlit_main(args=streamlit_args(port), prog_name="streamlit", standalone_mode=False)
    return 0


def child_command(port: int) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--streamlit-child", str(port)]
    return [sys.executable, str(Path(__file__).resolve()), "--streamlit-child", str(port)]


class DashboardLauncher:
    def __init__(self, root) -> None:
        self.root = root
        self.root.title("Painel Eleições 2026 · Ceará")
        self.root.resizable(False, False)
        self.port = free_loopback_port()
        self.child: subprocess.Popen | None = None
        self.log_handle = None
        self.ready = False
        self.started_at = time.monotonic()
        self.status = tk.StringVar(value="Iniciando o painel local…")
        tk.Label(root, text="Painel local · Ceará 2026", font=("Segoe UI", 13, "bold")).pack(padx=24, pady=(20, 8))
        tk.Label(root, textvariable=self.status, wraplength=390, justify="left").pack(padx=24, pady=(0, 14), anchor="w")
        buttons = tk.Frame(root)
        buttons.pack(padx=24, pady=(0, 20), fill="x")
        self.open_button = tk.Button(buttons, text="Abrir painel", command=self.open_panel, state="disabled", width=19)
        self.open_button.pack(side="left")
        tk.Button(buttons, text="Encerrar e fechar", command=self.close, width=19).pack(side="right")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.start_child()
        self.root.after(250, self.check_child)

    def start_child(self) -> None:
        log_dir = user_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "dashboard.log"
        self.log_handle = log_path.open("ab", buffering=0)
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.child = subprocess.Popen(
                child_command(self.port), stdin=subprocess.DEVNULL,
                stdout=self.log_handle, stderr=subprocess.STDOUT,
                cwd=str(resource_root()), close_fds=True, **kwargs,
            )
        except Exception:
            self.log_handle.close()
            self.log_handle = None
            raise
        self.status.set(f"Preparando painel em {health_url(self.port)}")

    def check_child(self) -> None:
        if self.child is None:
            return
        if self.child.poll() is not None:
            self.status.set(f"O painel encerrou. Consulte o log: {user_data_dir() / 'logs' / 'dashboard.log'}")
            return
        try:
            with urllib.request.urlopen(health_url(self.port), timeout=0.4) as response:
                if response.status == 200:
                    self.ready = True
                    self.open_button.configure(state="normal")
                    self.status.set("Painel pronto. A conexão aceita somente acessos deste computador.")
                    self.open_panel()
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        if time.monotonic() - self.started_at > 60:
            self.status.set(f"O servidor ainda não iniciou. Consulte o log: {user_data_dir() / 'logs' / 'dashboard.log'}")
        self.root.after(350, self.check_child)

    def open_panel(self) -> None:
        if self.ready:
            webbrowser.open(health_url(self.port).removesuffix(HEALTH_PATH))

    def close(self) -> None:
        child = self.child
        self.child = None
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
        self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--streamlit-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("port", nargs="?", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.streamlit_child:
        if not args.port:
            parser.error("--streamlit-child requer uma porta")
        return run_streamlit_child(args.port)
    if tk is None:
        raise RuntimeError("Tkinter não está disponível neste Python")
    root = tk.Tk()
    DashboardLauncher(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
