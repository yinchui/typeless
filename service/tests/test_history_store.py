from __future__ import annotations

from pathlib import Path

import pytest

from voice_text_organizer.history_store import HistoryStore


def test_manual_term_add_returns_pending_and_existed_state(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.db")

    created = store.add_manual_term("Typeless")
    assert created["ok"] is True
    assert created["term"] == "Typeless"
    assert created["existed"] is False
    assert created["sample_count"] == 0
    assert created["status"] == "pending"

    existed = store.add_manual_term("Typeless")
    assert existed["ok"] is True
    assert existed["term"] == "Typeless"
    assert existed["existed"] is True
    assert existed["sample_count"] == 0
    assert existed["status"] == "pending"


def test_samples_update_status_and_limit(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.db")
    store.add_manual_term("Kubernetes")

    first_sample_id = None
    for _ in range(5):
        sample = store.add_term_sample(
            term="Kubernetes",
            audio_path=str(tmp_path / "sample.wav"),
            duration_ms=680,
            quality_score=0.93,
            mfcc_fingerprint=b"test-fp",
        )
        if first_sample_id is None:
            first_sample_id = sample["sample_id"]
        assert sample["status"] == "active"

    with pytest.raises(ValueError, match="sample limit"):
        store.add_term_sample(
            term="Kubernetes",
            audio_path=str(tmp_path / "sample-overflow.wav"),
            duration_ms=700,
            quality_score=0.95,
            mfcc_fingerprint=b"test-fp-2",
        )

    deleted = store.delete_term_sample("Kubernetes", int(first_sample_id))
    assert deleted["ok"] is True
    assert deleted["sample_count"] == 4
    assert deleted["status"] == "active"


def test_export_terms_blob_supports_status_filter(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.db")
    store.add_manual_term("PendingWord")
    store.add_manual_term("ActiveWord")
    store.add_term_sample(
        term="ActiveWord",
        audio_path=str(tmp_path / "active.wav"),
        duration_ms=900,
        quality_score=0.91,
        mfcc_fingerprint=b"active-fp",
    )

    all_blob = store.export_terms_blob(status="all", limit=20)
    assert "PendingWord\t0\tpending" in all_blob
    assert "ActiveWord\t1\tactive" in all_blob

    active_blob = store.export_terms_blob(status="active", limit=20)
    assert "PendingWord" not in active_blob
    assert "ActiveWord\t1\tactive" in active_blob

    pending_blob = store.export_terms_blob(status="pending", limit=20)
    assert "ActiveWord" not in pending_blob
    assert "PendingWord\t0\tpending" in pending_blob


def test_delete_term_cascades_samples_and_files(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.db")
    store.add_manual_term("DeleteMe")

    sample_file = tmp_path / "sample-delete.wav"
    sample_file.write_bytes(b"fake audio")
    store.add_term_sample(
        term="DeleteMe",
        audio_path=str(sample_file),
        duration_ms=800,
        quality_score=0.96,
        mfcc_fingerprint=b"x",
    )

    deleted = store.delete_term("DeleteMe")
    assert deleted is True
    assert not sample_file.exists()
    assert "DeleteMe" not in store.export_terms_blob(status="all", limit=20)


def test_record_transcript_no_longer_auto_adds_terms(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "history.db")
    store.record_transcript(
        mode="cloud",
        voice_text="spoken",
        final_text="Kubernetes release note",
        duration_seconds=12,
    )

    blob = store.export_terms_blob(status="all", limit=20)
    assert "Kubernetes" not in blob
