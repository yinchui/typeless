from __future__ import annotations

from voice_text_organizer.runtime_paths import resolve_runtime_dir


def test_runtime_dir_prefers_explicit_env(monkeypatch) -> None:
    monkeypatch.setenv("VTO_RUNTIME_DIR", r"D:\tmp\vto-runtime")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\someone\AppData\Local")

    runtime_dir = resolve_runtime_dir()

    assert str(runtime_dir) == r"D:\tmp\vto-runtime"


def test_runtime_dir_uses_localappdata(monkeypatch) -> None:
    monkeypatch.delenv("VTO_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\someone\AppData\Local")

    runtime_dir = resolve_runtime_dir()

    assert str(runtime_dir).endswith(r"Typeless\runtime")
