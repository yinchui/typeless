import pytest

from voice_text_organizer.config import Settings
from voice_text_organizer.providers.siliconflow import rewrite_with_siliconflow


class _DummyResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "ok result"}}]}


def test_rewrite_requires_api_key() -> None:
    settings = Settings(default_mode="local")
    settings.siliconflow_api_key = None
    with pytest.raises(ValueError):
        rewrite_with_siliconflow([{"role": "user", "content": "x"}], settings=settings)


def test_rewrite_sends_messages_list(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _DummyResponse()

    monkeypatch.setattr("voice_text_organizer.providers.siliconflow.httpx.post", fake_post)
    settings = Settings(default_mode="cloud", siliconflow_api_key="test-key")
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Test input"},
    ]

    result = rewrite_with_siliconflow(messages, settings=settings)

    assert result == "ok result"
    call_json = captured["kwargs"]["json"]  # type: ignore[index]
    assert call_json["messages"] == messages  # type: ignore[index]

