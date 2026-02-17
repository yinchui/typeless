from fastapi.testclient import TestClient

from voice_text_organizer.main import app


def test_selected_text_non_whitelist_returns_transcription(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rewrite should not be called")),
    )

    start_response = client.post("/v1/session/start", json={"selected_text": "old"})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    stop_response = client.post(
        "/v1/session/stop",
        json={"session_id": session_id, "voice_text": "rewrite this", "mode": "local"},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["final_text"] == "rewrite this"


def test_stop_short_plain_text_bypasses_rewrite(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rewrite should be bypassed")),
    )

    start_response = client.post("/v1/session/start", json={})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    stop_response = client.post(
        "/v1/session/stop",
        json={"session_id": session_id, "voice_text": "ok", "mode": "cloud"},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["final_text"] == "ok"


def test_session_stop_without_selected_text_uses_transcription_only(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rewrite should not be called")),
    )

    start_response = client.post("/v1/session/start", json={"existing_text": "existing editor text"})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    voice_text = "请问今天上海天气怎么样"
    stop_response = client.post(
        "/v1/session/stop",
        json={"session_id": session_id, "voice_text": voice_text, "mode": "cloud"},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["final_text"] == voice_text


def test_session_stop_selected_text_translate_command_uses_rewrite(monkeypatch) -> None:
    client = TestClient(app)

    observed = {"called": False}

    def fake_route(*_args, **_kwargs):
        observed["called"] = True
        return "你好，世界"

    monkeypatch.setattr("voice_text_organizer.main.route_rewrite", fake_route)

    start_response = client.post("/v1/session/start", json={"selected_text": "hello world"})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    stop_response = client.post(
        "/v1/session/stop",
        json={"session_id": session_id, "voice_text": "翻译成中文", "mode": "cloud"},
    )
    assert stop_response.status_code == 200
    assert observed["called"] is True
    assert stop_response.json()["final_text"] == "你好，世界"
