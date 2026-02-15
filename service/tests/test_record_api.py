from pathlib import Path


def test_record_start_and_stop_returns_voice_and_final_text(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": "spoken words",
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.local_provider", lambda _prompt: "clean result", raising=False)

    def fake_stop(_session_id: str) -> Path:
        return Path("dummy.wav")

    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", fake_stop, raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)

    start = client.post("/v1/record/start", json={"selected_text": "old"})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "local"})
    assert stop.status_code == 200
    assert stop.json()["voice_text"] == "spoken words"
    assert stop.json()["final_text"] == "clean result"
