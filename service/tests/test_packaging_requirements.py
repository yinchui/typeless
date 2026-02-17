from __future__ import annotations

import re
from pathlib import Path


def test_numpy_is_declared_as_runtime_dependency() -> None:
    """Installer/runtime backend needs numpy for sounddevice recording."""
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject_raw = pyproject_path.read_text(encoding="utf-8")

    assert re.search(r'"numpy[^"]*"', pyproject_raw), "numpy must be declared in dependencies"
