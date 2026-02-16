from __future__ import annotations

import re
from pathlib import Path


def _read_project_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        raw = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"

    in_project_section = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project_section = stripped == "[project]"
            continue
        if not in_project_section:
            continue
        match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
        if match:
            return match.group(1)
    return "0.0.0"


CURRENT_VERSION = _read_project_version()
