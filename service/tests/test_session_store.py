from voice_text_organizer.session_store import SessionStore


def test_create_and_get_session() -> None:
    store = SessionStore()
    session_id = store.create(selected_text="old text")
    session = store.get(session_id)

    assert session.selected_text == "old text"


def test_create_session_with_existing_text() -> None:
    store = SessionStore()
    session_id = store.create(selected_text=None, existing_text="Hello world")
    session = store.get(session_id)

    assert session.existing_text == "Hello world"
    assert session.selected_text is None


def test_create_session_existing_text_defaults_none() -> None:
    store = SessionStore()
    session_id = store.create()
    session = store.get(session_id)

    assert session.existing_text is None
