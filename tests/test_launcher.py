from pathlib import Path

import launcher


def test_local_runtime_arguments_and_resource_root():
    root = launcher.resource_root()
    assert root == Path(launcher.__file__).resolve().parent
    assert (root / "dashboard.py").is_file()
    args = launcher.streamlit_args(8765)
    assert args[0:2] == ["run", str(root / "dashboard.py")]
    assert "--server.address=127.0.0.1" in args
    assert "--server.port=8765" in args
    assert launcher.health_url(8765) == "http://127.0.0.1:8765/_stcore/health"


def test_child_command_uses_current_python_in_development(monkeypatch):
    monkeypatch.setattr(launcher.sys, "frozen", False, raising=False)
    command = launcher.child_command(12345)
    assert command[0] == launcher.sys.executable
    assert command[1] == str(Path(launcher.__file__).resolve())
    assert command[-2:] == ["--streamlit-child", "12345"]


def test_frozen_resources_and_child_reexec_use_bundled_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.sys, "frozen", True, raising=False)
    monkeypatch.setattr(launcher.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(launcher.sys, "executable", str(tmp_path / "CE2026Dashboard.exe"))
    assert launcher.resource_root() == tmp_path
    assert launcher.streamlit_args(9000)[1] == str(tmp_path / "dashboard.py")
    assert launcher.child_command(9000) == [str(tmp_path / "CE2026Dashboard.exe"), "--streamlit-child", "9000"]


def test_free_port_is_local_and_bindable():
    port = launcher.free_loopback_port()
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
