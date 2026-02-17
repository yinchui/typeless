from fastapi.testclient import TestClient

from voice_text_organizer.main import app
from voice_text_organizer.template_classifier import TemplateClassification


def test_selected_text_non_command_returns_light_edit(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "voice_text_organizer.main.classify_template",
        lambda *_args, **_kwargs: TemplateClassification(
            template="meeting_minutes",
            confidence=0.51,
            reason="insufficient_signal",
        ),
    )
    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rewrite should not be called")),
    )

    start_response = client.post("/v1/session/start", json={"selected_text": "old"})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    voice_text = "please summarize this"
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
        json={"session_id": session_id, "voice_text": "translate to chinese", "mode": "cloud"},
    )
    assert stop_response.status_code == 200
    assert observed["called"] is True
    assert stop_response.json()["final_text"] == "你好，世界"


def test_session_stop_explicit_meeting_command_uses_rewrite(monkeypatch) -> None:
    client = TestClient(app)

    observed = {"called": False}

    def fake_route(*_args, **_kwargs):
        observed["called"] = True
        return "Topic: Release\n\nAction Items:\n- Ship beta"

    monkeypatch.setattr("voice_text_organizer.main.route_rewrite", fake_route)

    start_response = client.post("/v1/session/start", json={})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    stop_response = client.post(
        "/v1/session/stop",
        json={
            "session_id": session_id,
            "voice_text": "请按会议纪要整理 今天讨论发布计划",
            "mode": "cloud",
        },
    )
    assert stop_response.status_code == 200
    assert observed["called"] is True
    assert "Topic" in stop_response.json()["final_text"]


def test_session_stop_classifier_low_confidence_falls_back_light_edit(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "voice_text_organizer.main.classify_template",
        lambda *_args, **_kwargs: TemplateClassification(
            template="task_list",
            confidence=0.61,
            reason="low_confidence",
        ),
    )
    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rewrite should not be called")),
    )

    start_response = client.post("/v1/session/start", json={})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    voice_text = "we should check docs and follow up tomorrow"
    stop_response = client.post(
        "/v1/session/stop",
        json={"session_id": session_id, "voice_text": voice_text, "mode": "cloud"},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["final_text"] == voice_text


def test_session_stop_template_rewrite_error_falls_back_to_light_edit(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "voice_text_organizer.main.classify_template",
        lambda *_args, **_kwargs: TemplateClassification(
            template="task_list",
            confidence=0.93,
            reason="strong_task_signal",
        ),
    )
    monkeypatch.setattr(
        "voice_text_organizer.main.route_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("rewrite backend down")),
    )

    start_response = client.post("/v1/session/start", json={})
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    voice_text = "list tasks for release"
    stop_response = client.post(
        "/v1/session/stop",
        json={"session_id": session_id, "voice_text": voice_text, "mode": "cloud"},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["final_text"] == voice_text
