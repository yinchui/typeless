def test_e2e_session_flow_with_mocked_dependencies(client, monkeypatch) -> None:
    monkeypatch.setattr("voice_text_organizer.main.cloud_provider", lambda _prompt: "clean result")

    start = client.post("/v1/session/start", json={"selected_text": "old text"})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post(
        "/v1/session/stop",
        json={"session_id": session_id, "voice_text": "translate to chinese", "mode": "cloud"},
    )
    assert stop.status_code == 200
    assert stop.json()["final_text"] == "clean result"
