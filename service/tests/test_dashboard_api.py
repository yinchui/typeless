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
        lambda **kwargs: "Kubernetes\tauto\t3\nTypeless\tmanual\t1",
        raising=False,
    )

    res = client.get("/v1/dashboard/terms/export")
    assert res.status_code == 200
    assert "Kubernetes" in res.json()["terms_blob"]


def test_dashboard_manual_term_rejects_empty(client) -> None:
    res = client.post("/v1/dashboard/terms/manual", json={"term": "   "})
    assert res.status_code == 422
