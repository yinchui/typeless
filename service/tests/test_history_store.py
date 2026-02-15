from pathlib import Path

from voice_text_organizer.history_store import HistoryStore


def test_history_store_persists_summary_and_terms(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    store = HistoryStore(db_path)

    store.record_transcript(
        mode="cloud",
        voice_text="first",
        final_text="请同步 Kubernetes 配置",
        duration_seconds=30,
    )
    store.record_transcript(
        mode="cloud",
        voice_text="second",
        final_text="今天继续同步 Kubernetes 配置",
        duration_seconds=45,
    )

    summary = store.get_summary()
    assert summary["transcript_count"] == 2
    assert summary["total_duration_seconds"] == 75
    assert summary["total_chars"] >= 2

    blob = store.export_terms_blob(min_auto_count=2)
    assert "Kubernetes" in blob
    assert "\tauto\t" in blob


def test_history_store_manual_term_is_always_visible(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    store = HistoryStore(db_path)

    store.add_manual_term("Typeless")
    blob = store.export_terms_blob(min_auto_count=5)

    assert "Typeless\tmanual\t1" in blob
