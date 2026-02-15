from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from uuid import uuid4


@dataclass
class Session:
    session_id: str
    selected_text: str | None = None


class SessionStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._data: dict[str, Session] = {}

    def create(self, selected_text: str | None = None) -> str:
        session_id = str(uuid4())
        with self._lock:
            self._data[session_id] = Session(
                session_id=session_id,
                selected_text=selected_text,
            )
        return session_id

    def get(self, session_id: str) -> Session:
        with self._lock:
            return self._data[session_id]
