from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from voice_text_organizer.asr import normalize_asr_text, transcribe_with_siliconflow
from voice_text_organizer.audio import AudioRecorder
from voice_text_organizer.config import Settings
from voice_text_organizer.providers.ollama import rewrite_with_ollama
from voice_text_organizer.providers.siliconflow import rewrite_with_siliconflow
from voice_text_organizer.rewrite import build_prompt
from voice_text_organizer.router import route_rewrite
from voice_text_organizer.schemas import (
    StartSessionRequest,
    StartSessionResponse,
    SettingsUpdateRequest,
    SettingsViewResponse,
    StopRecordRequest,
    StopRecordResponse,
    StopSessionRequest,
    StopSessionResponse,
)
from voice_text_organizer.session_store import SessionStore

RUNTIME_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "runtime" / "settings.json"


def _load_runtime_settings(path: Path | None = None) -> dict[str, str | None]:
    settings_path = path or RUNTIME_SETTINGS_PATH
    if not settings_path.exists():
        return {}

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    result: dict[str, str | None] = {}
    if payload.get("default_mode") in ("cloud", "local"):
        result["default_mode"] = payload["default_mode"]
    if "siliconflow_api_key" in payload:
        value = payload["siliconflow_api_key"]
        if value is None:
            result["siliconflow_api_key"] = None
        elif isinstance(value, str):
            cleaned = value.strip()
            result["siliconflow_api_key"] = cleaned or None
    return result


def _save_runtime_settings(payload: dict[str, str | None], path: Path | None = None) -> None:
    settings_path = path or RUNTIME_SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def _mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    tail = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"****{tail}"


def _build_settings_view() -> SettingsViewResponse:
    return SettingsViewResponse(
        default_mode=settings.default_mode,
        api_key_configured=bool(settings.siliconflow_api_key),
        api_key_masked=_mask_api_key(settings.siliconflow_api_key),
    )


def _persist_current_settings() -> None:
    _save_runtime_settings(
        {
            "default_mode": settings.default_mode,
            "siliconflow_api_key": settings.siliconflow_api_key,
        }
    )


def _load_settings() -> Settings:
    default_mode = os.getenv("VTO_DEFAULT_MODE", "cloud")
    try:
        current = Settings(default_mode=default_mode)
    except ValueError:
        current = Settings(default_mode="local")

    runtime_overrides = _load_runtime_settings()
    if runtime_overrides.get("default_mode") in ("cloud", "local"):
        current.default_mode = runtime_overrides["default_mode"]  # type: ignore[assignment]
    if "siliconflow_api_key" in runtime_overrides:
        current.siliconflow_api_key = runtime_overrides["siliconflow_api_key"]
    return current


settings = _load_settings()
store = SessionStore()
recorder = AudioRecorder()


def cloud_provider(prompt: str) -> str:
    return rewrite_with_siliconflow(prompt, settings=settings)


def local_provider(prompt: str) -> str:
    return rewrite_with_ollama(prompt, settings=settings)


def transcribe_audio(audio_path: Path, language_hint: str = "auto") -> str:
    return transcribe_with_siliconflow(
        audio_path=audio_path,
        settings=settings,
        language=language_hint,
    )


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


app = FastAPI()

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/settings", response_model=SettingsViewResponse)
def get_settings() -> SettingsViewResponse:
    return _build_settings_view()


@app.put("/v1/settings", response_model=SettingsViewResponse)
def update_settings(payload: SettingsUpdateRequest) -> SettingsViewResponse:
    if payload.default_mode is not None:
        settings.default_mode = payload.default_mode

    if payload.api_key is not None:
        cleaned = payload.api_key.strip()
        settings.siliconflow_api_key = cleaned or None

    try:
        _persist_current_settings()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to persist settings: {exc}",
        ) from exc
    return _build_settings_view()


@app.post("/v1/session/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest) -> StartSessionResponse:
    session_id = store.create(selected_text=payload.selected_text)
    return StartSessionResponse(session_id=session_id)


@app.post("/v1/record/start", response_model=StartSessionResponse)
def start_record(payload: StartSessionRequest) -> StartSessionResponse:
    session_id = store.create(selected_text=payload.selected_text)
    try:
        recorder.start(session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to start recording: {exc}") from exc
    return StartSessionResponse(session_id=session_id)


@app.post("/v1/session/stop", response_model=StopSessionResponse)
def stop_session(payload: StopSessionRequest) -> StopSessionResponse:
    try:
        session = store.get(payload.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    voice_text = normalize_asr_text(payload.voice_text)
    if not voice_text:
        raise HTTPException(status_code=422, detail="voice_text is empty")

    prompt = build_prompt(voice_text, selected_text=session.selected_text)
    final_text = route_rewrite(
        prompt,
        cloud_fn=cloud_provider,
        local_fn=local_provider,
        default_mode=payload.mode or settings.default_mode,
        fallback=settings.fallback_to_local_on_cloud_error,
    )
    return StopSessionResponse(final_text=final_text)


@app.post("/v1/record/stop", response_model=StopRecordResponse)
def stop_record(payload: StopRecordRequest) -> StopRecordResponse:
    try:
        session = store.get(payload.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    try:
        audio_path = recorder.stop(payload.session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to stop recording: {exc}") from exc

    try:
        voice_text = normalize_asr_text(
            transcribe_audio(audio_path, language_hint=payload.language_hint)
        )
        if not voice_text:
            raise HTTPException(status_code=422, detail="no speech detected")

        prompt = build_prompt(voice_text, selected_text=session.selected_text)
        final_text = route_rewrite(
            prompt,
            cloud_fn=cloud_provider,
            local_fn=local_provider,
            default_mode=payload.mode or settings.default_mode,
            fallback=settings.fallback_to_local_on_cloud_error,
        )
        return StopRecordResponse(voice_text=voice_text, final_text=final_text)
    finally:
        _safe_unlink(audio_path)
