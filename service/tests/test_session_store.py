from voice_text_organizer.session_store import SessionStore


def test_create_and_get_session() -> None:
    store = SessionStore()
    session_id = store.create(selected_text="old text")
    session = store.get(session_id)

    assert session.selected_text == "old text"
