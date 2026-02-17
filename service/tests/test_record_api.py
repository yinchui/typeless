from pathlib import Path

from voice_text_organizer.main import store
from voice_text_organizer.template_classifier import TemplateClassification


def test_record_start_and_stop_returns_voice_and_final_text(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": "spoken words",
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.recorder.stop",
        lambda _session_id: Path("dummy.wav"),
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: "spoken words",
        raising=False,
    )
    monkeypatch.setattr(
        "voice_text_organizer.main.classify_template",
        lambda *_args, **_kwargs: TemplateClassification(
            template="meeting_minutes",
            confidence=0.40,
            reason="low_confidence",
        ),
        raising=False,
    )

    start = client.post("/v1/record/start", json={})
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
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)

    state = {"stopped": False}

    def fake_stop(_session_id: str) -> Path:
        if state["stopped"]:
            raise KeyError(_session_id)
        state["stopped"] = True
        return Path("dummy.wav")

    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", fake_stop, raising=False)

    start = client.post("/v1/record/start", json={})
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
        json={"selected_text": None, "existing_text": "existing editor content"},
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    session = store.get(session_id)
    assert session.existing_text == "existing editor content"


def test_record_stop_selected_text_translate_command_uses_rewrite(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": "translate to chinese",
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


def test_record_stop_explicit_task_command_uses_rewrite(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.transcribe_audio",
        lambda _path, language_hint="auto": "请整理成任务清单 并分配负责人",
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", lambda _session_id: Path("dummy.wav"), raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)

    observed = {"called": False}

    def fake_route(*_args, **_kwargs):
        observed["called"] = True
        return "- 整理发布说明\n- 指定负责人"

    monkeypatch.setattr("voice_text_organizer.main.route_rewrite", fake_route, raising=False)

    start = client.post("/v1/record/start", json={})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "cloud"})
    assert stop.status_code == 200
    assert observed["called"] is True
    assert "指定负责人" in stop.json()["final_text"]


def test_record_stop_classifier_low_confidence_falls_back_light_edit(client, monkeypatch) -> None:
    voice_text = "we should sync with design team tomorrow"
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
        "voice_text_organizer.main.classify_template",
        lambda *_args, **_kwargs: TemplateClassification(
            template="meeting_minutes",
            confidence=0.55,
            reason="low_confidence",
        ),
        raising=False,
    )
    observed = {"called": False}

    def fake_route(*_args, **_kwargs):
        observed["called"] = True
        return "Sync with design team tomorrow."

    monkeypatch.setattr("voice_text_organizer.main.route_rewrite", fake_route, raising=False)

    start = client.post("/v1/record/start", json={})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "cloud"})
    assert stop.status_code == 200
    assert stop.json()["voice_text"] == voice_text
    assert observed["called"] is True
    assert stop.json()["final_text"] == "Sync with design team tomorrow."


def test_record_stop_template_rewrite_error_falls_back_to_light_edit(client, monkeypatch) -> None:
    voice_text = "list tasks for release"
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
        "voice_text_organizer.main.classify_template",
        lambda *_args, **_kwargs: TemplateClassification(
            template="task_list",
            confidence=0.93,
            reason="strong_task_signal",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("rewrite backend down")),
        raising=False,
    )

    start = client.post("/v1/record/start", json={})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "cloud"})
    assert stop.status_code == 200
    assert stop.json()["voice_text"] == voice_text
    assert stop.json()["final_text"] == voice_text


def test_record_stop_default_language_hint_prefers_chinese(client, monkeypatch) -> None:
    observed: dict[str, str] = {}

    def fake_transcribe(_path, language_hint="auto"):
        observed["language_hint"] = language_hint
        return "中文转录结果"

    monkeypatch.setattr("voice_text_organizer.main.transcribe_audio", fake_transcribe, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", lambda _session_id: Path("dummy.wav"), raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.route_rewrite", lambda *_args, **_kwargs: "中文转录结果", raising=False)

    start = client.post("/v1/record/start", json={})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post("/v1/record/stop", json={"session_id": session_id, "mode": "cloud"})
    assert stop.status_code == 200
    assert observed["language_hint"] == "zh"


def test_record_stop_honors_explicit_language_hint(client, monkeypatch) -> None:
    observed: dict[str, str] = {}

    def fake_transcribe(_path, language_hint="auto"):
        observed["language_hint"] = language_hint
        return "english transcript"

    monkeypatch.setattr("voice_text_organizer.main.transcribe_audio", fake_transcribe, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", lambda _session_id: Path("dummy.wav"), raising=False)
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.history_store.record_transcript", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.route_rewrite", lambda *_args, **_kwargs: "english transcript", raising=False)

    start = client.post("/v1/record/start", json={})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post(
        "/v1/record/stop",
        json={"session_id": session_id, "mode": "cloud", "language_hint": "en"},
    )
    assert stop.status_code == 200
    assert observed["language_hint"] == "en"
