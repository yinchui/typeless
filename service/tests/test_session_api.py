from fastapi.testclient import TestClient

from voice_text_organizer.main import app


def test_start_and_stop_returns_final_text(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "voice_text_organizer.main.local_provider",
        lambda _prompt: "final text",
    )

    start_response = client.post("/v1/session/start", json={"selected_text": "old"})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    stop_response = client.post(
        "/v1/session/stop",
        json={"session_id": session_id, "voice_text": "rewrite this", "mode": "local"},
    )
    assert stop_response.status_code == 200
    assert "final_text" in stop_response.json()
