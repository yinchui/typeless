from __future__ import annotations

from datetime import datetime, timedelta, timezone

from voice_text_organizer.version_check import resolve_version


def _as_zulu(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_resolve_version_uses_fresh_cache_without_network(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    runtime_settings = {
        "last_update_check_at": _as_zulu(now - timedelta(hours=1)),
        "last_release_version": "0.2.0",
        "last_release_url": "https://example.com/release",
    }

    def fail_network(*_args, **_kwargs):
        raise AssertionError("network should not be called when cache is fresh")

    monkeypatch.setattr("voice_text_organizer.version_check.httpx.get", fail_network)

    result = resolve_version(current_version="0.1.0", runtime_settings=runtime_settings)

    assert result.latest_version == "0.2.0"
    assert result.has_update is True
    assert result.release_url == "https://example.com/release"


def test_resolve_version_fetches_latest_release(monkeypatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "tag_name": "v0.3.0",
                "html_url": "https://github.com/yinchui/typeless/releases/tag/v0.3.0",
            }

    monkeypatch.setattr(
        "voice_text_organizer.version_check.httpx.get",
        lambda *_args, **_kwargs: DummyResponse(),
    )

    result = resolve_version(current_version="0.1.0", runtime_settings={})

    assert result.latest_version == "0.3.0"
    assert result.has_update is True
    assert "v0.3.0" in result.release_url
