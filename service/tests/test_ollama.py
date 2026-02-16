import pytest

from voice_text_organizer.config import Settings
from voice_text_organizer.providers.ollama import rewrite_with_ollama


class _DummyResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"message": {"content": "ollama result"}}


def test_rewrite_sends_messages_to_chat_api(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _DummyResponse()

    monkeypatch.setattr("voice_text_organizer.providers.ollama.httpx.post", fake_post)
    settings = Settings(default_mode="local")
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Test input"},
    ]

    result = rewrite_with_ollama(messages, settings=settings)

    assert result == "ollama result"
    assert str(captured["url"]).endswith("/api/chat")
    call_json = captured["kwargs"]["json"]  # type: ignore[index]
    assert call_json["messages"] == messages  # type: ignore[index]

