# Voice Text Organizer Service

FastAPI backend for recording, transcription, rewrite routing, and session APIs.

## Runtime Path

Service runtime files are stored in:
- `%LOCALAPPDATA%\Typeless\runtime` by default
- custom directory when `VTO_RUNTIME_DIR` is set

## Release API

- `GET /v1/app/version` returns current version, latest release version, update flag, release URL and check timestamp.
