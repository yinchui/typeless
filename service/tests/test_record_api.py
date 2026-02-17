from pathlib import Path


def test_record_start_and_stop_returns_voice_and_final_text(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": "spoken words",
        raising=False,
    )

    def fake_stop(_session_id: str) -> Path:
        return Path("dummy.wav")

    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", fake_stop, raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)

    start = client.post("/v1/record/start", json={"selected_text": "old"})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "local"})
    assert stop.status_code == 200
    assert stop.json()["voice_text"] == "spoken words"
    assert stop.json()["final_text"] == "spoken words"


def test_record_stop_duplicate_call_returns_404(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": "spoken words",
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.local_provider", lambda _prompt: "clean result", raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)

    state = {"stopped": False}

    def fake_stop(_session_id: str) -> Path:
        if state["stopped"]:
            raise KeyError(_session_id)
        state["stopped"] = True
        return Path("dummy.wav")

    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", fake_stop, raising=False)

    start = client.post("/v1/record/start", json={"selected_text": "old"})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    first_stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "local"})
    assert first_stop.status_code == 200

    second_stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "local"})
    assert second_stop.status_code == 404
    assert "already stopped" in second_stop.json()["detail"]


def test_start_record_accepts_existing_text(client, monkeypatch) -> None:
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)

    response = client.post(
        "/v1/record/start",
        json={"selected_text": None, "existing_text": "前面已有的文字"},
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    from voice_text_organizer.main import store

    session = store.get(session_id)
    assert session.existing_text == "前面已有的文字"


def test_record_stop_short_plain_text_bypasses_rewrite(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": "你好",
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", lambda _session_id: Path("dummy.wav"), raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rewrite should be bypassed")),
        raising=False,
    )

    start = client.post("/v1/record/start", json={})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "cloud"})
    assert stop.status_code == 200
    assert stop.json()["voice_text"] == "你好"
    assert stop.json()["final_text"] == "你好"

def test_record_stop_without_selected_text_uses_transcription_only(client, monkeypatch) -> None:
    voice_text = "请问今天上海天气怎么样"
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": voice_text,
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", lambda _session_id: Path("dummy.wav"), raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rewrite should not be called")),
        raising=False,
    )

    start = client.post("/v1/record/start", json={"existing_text": "existing editor text"})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "cloud"})
    assert stop.status_code == 200
    assert stop.json()["voice_text"] == voice_text
    assert stop.json()["final_text"] == voice_text


def test_record_stop_selected_text_translate_command_uses_rewrite(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": "翻译成中文",
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", lambda _session_id: Path("dummy.wav"), raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)

    observed = {"called": False}

    def fake_route(*_args, **_kwargs):
        observed["called"] = True
        return "你好，世界"

    monkeypatch.setattr("voice_text_organizer.main.route_rewrite", fake_route, raising=False)

    start = client.post("/v1/record/start", json={"selected_text": "hello world"})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "cloud"})
    assert stop.status_code == 200
    assert observed["called"] is True
    assert stop.json()["final_text"] == "你好，世界"


def test_record_stop_selected_text_non_whitelist_is_transcription_only(client, monkeypatch) -> None:
    voice_text = "帮我总结一下"
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": voice_text,
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", lambda _session_id: Path("dummy.wav"), raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rewrite should not be called")),
        raising=False,
    )

    start = client.post("/v1/record/start", json={"selected_text": "hello world"})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "cloud"})
    assert stop.status_code == 200
    assert stop.json()["voice_text"] == voice_text
    assert stop.json()["final_text"] == voice_text
