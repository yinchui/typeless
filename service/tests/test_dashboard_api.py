from __future__ import annotations

from pathlib import Path


def test_dashboard_summary_endpoint(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.get_summary",
        lambda: {
            "transcript_count": 3,
            "total_duration_seconds": 120,
            "total_chars": 450,
            "average_chars_per_minute": 225,
            "saved_seconds": 252,
            "profile_score": 18,
        },
        raising=False,
    )

    res = client.get("/v1/dashboard/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["transcript_count"] == 3
    assert body["total_chars"] == 450


def test_dashboard_terms_export_endpoint(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.export_terms_blob",
        lambda **kwargs: "Kubernetes\t2\tactive\nTypeless\t0\tpending",
        raising=False,
    )

    res = client.get("/v1/dashboard/terms/export?status=all")
    assert res.status_code == 200
    assert "Kubernetes" in res.json()["terms_blob"]
    assert "active" in res.json()["terms_blob"]


def test_dashboard_manual_term_rejects_empty(client) -> None:
    res = client.post("/v1/dashboard/terms/manual", json={"term": "   "})
    assert res.status_code == 422


def test_dashboard_manual_term_returns_status(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.add_manual_term",
        lambda term: {
            "ok": True,
            "term": term,
            "existed": False,
            "sample_count": 0,
            "status": "pending",
        },
        raising=False,
    )

    res = client.post("/v1/dashboard/terms/manual", json={"term": "Typeless"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True
    assert payload["term"] == "Typeless"
    assert payload["status"] == "pending"


def test_dashboard_delete_term_endpoint(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.delete_term",
        lambda term: term == "Kubernetes",
        raising=False,
    )

    res = client.post("/v1/dashboard/terms/delete", json={"term": "Kubernetes"})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["deleted"] is True


def test_dashboard_delete_term_rejects_empty(client) -> None:
    res = client.post("/v1/dashboard/terms/delete", json={"term": "   "})
    assert res.status_code == 422


def test_dashboard_term_sample_start_and_stop(client, monkeypatch) -> None:
    monkeypatch.setattr("voice_text_organizer.main.recorder.start", lambda _session_id: None, raising=False)
    monkeypatch.setattr("voice_text_organizer.main.recorder.stop", lambda _session_id: Path("dummy.wav"), raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.add_manual_term",
        lambda term: {
            "ok": True,
            "term": term,
            "existed": False,
            "sample_count": 0,
            "status": "pending",
        },
        raising=False,
    )
    monkeypatch.setattr(
        "voice_text_organizer.main._evaluate_sample_audio_quality",
        lambda _path: {
            "duration_ms": 860,
            "quality_score": 0.91,
            "silence_ratio": 0.22,
            "rms": 0.08,
            "clipping_ratio": 0.0,
        },
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main.build_mfcc_fingerprint_bytes", lambda _path: b"mfcc", raising=False)
    monkeypatch.setattr(
        "voice_text_organizer.main._persist_term_sample_file",
        lambda term, session_id, source_path: Path(f"saved-{term}-{session_id}.wav"),
        raising=False,
    )
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.add_term_sample",
        lambda **kwargs: {
            "ok": True,
            "sample_id": 1,
            "sample_count": 1,
            "status": "active",
        },
        raising=False,
    )
    monkeypatch.setattr("voice_text_organizer.main._safe_unlink", lambda _path: None, raising=False)

    start = client.post("/v1/dashboard/terms/sample/start", json={"term": "Typeless"})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    stop = client.post(
        "/v1/dashboard/terms/sample/stop",
        json={"term": "Typeless", "session_id": session_id},
    )
    assert stop.status_code == 200
    payload = stop.json()
    assert payload["ok"] is True
    assert payload["sample_id"] == 1
    assert payload["sample_count"] == 1
    assert payload["status"] == "active"
    assert payload["duration_ms"] == 860


def test_dashboard_term_samples_export(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.export_term_samples_blob",
        lambda term: "1\t860\t2026-02-20T10:00:00Z\tC:/sample.wav",
        raising=False,
    )

    res = client.get("/v1/dashboard/terms/samples/export?term=Typeless")
    assert res.status_code == 200
    assert "C:/sample.wav" in res.json()["samples_blob"]


def test_dashboard_term_samples_export_post(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.export_term_samples_blob",
        lambda term: "2\t940\t2026-02-20T10:20:00Z\tC:/sample-2.wav",
        raising=False,
    )

    res = client.post("/v1/dashboard/terms/samples/export", json={"term": "Typeless"})
    assert res.status_code == 200
    assert "sample-2.wav" in res.json()["samples_blob"]


def test_dashboard_term_sample_delete(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_text_organizer.main.history_store.delete_term_sample",
        lambda term, sample_id: {
            "ok": True,
            "sample_count": 0,
            "status": "pending",
        },
        raising=False,
    )

    res = client.post("/v1/dashboard/terms/sample/delete", json={"term": "Typeless", "sample_id": 7})
    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True
    assert payload["sample_count"] == 0
    assert payload["status"] == "pending"


def test_term_sample_dir_uses_runtime_parent_recordings(monkeypatch, tmp_path: Path) -> None:
    from voice_text_organizer import main

    runtime_dir = tmp_path / "repo" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VTO_RUNTIME_DIR", str(runtime_dir))

    sample_dir = main._term_sample_dir("Typeless")
    expected_prefix = tmp_path / "repo" / "recordings" / "term_samples"
    assert str(sample_dir).startswith(str(expected_prefix))
