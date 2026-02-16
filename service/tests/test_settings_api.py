from __future__ import annotations

import json
from pathlib import Path


def test_get_settings_returns_masked_key(client, monkeypatch) -> None:
    monkeypatch.setattr("voice_text_organizer.main.settings.default_mode", "cloud", raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.settings.siliconflow_api_key",
        "sk-example-12345678",
        raising=False,
    )

    response = client.get("/v1/settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_mode"] == "cloud"
    assert payload["update_channel"] == "stable"
    assert payload["api_key_configured"] is True
    assert payload["api_key_masked"] == "****5678"


def test_put_settings_persists_and_applies_runtime(client, monkeypatch, tmp_path: Path) -> None:
    settings_path = tmp_path / "runtime" / "settings.json"
    monkeypatch.setattr("voice_text_organizer.main.RUNTIME_SETTINGS_PATH", settings_path, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.settings.default_mode", "local", raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.settings.siliconflow_api_key",
        None,
        raising=False,
    )

    response = client.put(
        "/v1/settings",
        json={"default_mode": "cloud", "api_key": "sk-new-abcdefg1234"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_mode"] == "cloud"
    assert payload["update_channel"] == "stable"
    assert payload["api_key_configured"] is True
    assert payload["api_key_masked"] == "****1234"

    assert settings_path.exists()
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["default_mode"] == "cloud"
    assert saved["update_channel"] == "stable"
    assert saved["siliconflow_api_key"] == "sk-new-abcdefg1234"
