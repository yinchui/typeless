from __future__ import annotations

import json
from pathlib import Path

from voice_text_organizer.version_check import VersionCheckResult


def test_app_version_endpoint_returns_and_caches(client, monkeypatch, tmp_path: Path) -> None:
    settings_path = tmp_path / "runtime" / "settings.json"
    monkeypatch.setattr("voice_text_organizer.main.RUNTIME_SETTINGS_PATH", settings_path, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.CURRENT_VERSION", "0.1.0", raising=False)
    monkeypatch.setattr("voice_text_organizer.main.settings.default_mode", "cloud", raising=False)
    monkeypatch.setattr("voice_text_organizer.main.settings.update_channel", "stable", raising=False)
    monkeypatch.setattr("voice_text_organizer.main.settings.siliconflow_api_key", "sk-demo", raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.resolve_version",
        lambda **_kwargs: VersionCheckResult(
            current_version="0.1.0",
            latest_version="0.2.0",
            has_update=True,
            release_url="https://github.com/yinchui/typeless/releases/tag/v0.2.0",
            checked_at="2026-02-16T12:00:00Z",
            cache_payload={
                "last_update_check_at": "2026-02-16T12:00:00Z",
                "last_release_version": "0.2.0",
                "last_release_url": "https://github.com/yinchui/typeless/releases/tag/v0.2.0",
            },
        ),
        raising=False,
    )

    response = client.get("/v1/app/version")
    assert response.status_code == 200

    payload = response.json()
    assert payload["current_version"] == "0.1.0"
    assert payload["latest_version"] == "0.2.0"
    assert payload["has_update"] is True
    assert "releases/tag/v0.2.0" in payload["release_url"]

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["default_mode"] == "cloud"
    assert saved["update_channel"] == "stable"
    assert saved["last_release_version"] == "0.2.0"
