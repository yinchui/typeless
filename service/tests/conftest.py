from fastapi.testclient import TestClient

from voice_text_organizer.main import app


def pytest_configure(config) -> None:  # pragma: no cover
    config.addinivalue_line("filterwarnings", "ignore:The 'app' shortcut is now deprecated")


def _build_client() -> TestClient:
    return TestClient(app)


import pytest


@pytest.fixture
def client() -> TestClient:
    return _build_client()
