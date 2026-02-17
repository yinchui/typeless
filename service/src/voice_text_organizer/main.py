from __future__ import annotations

import json
import logging
import os
import shutil
import wave
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException

from voice_text_organizer.asr import normalize_asr_text, transcribe_with_siliconflow
from voice_text_organizer.audio import AudioRecorder
from voice_text_organizer.config import Settings
from voice_text_organizer.history_store import HistoryStore
from voice_text_organizer.policy import (
    TemplateDecision,
    decide_template_from_classifier,
    is_whitelist_translation_command,
    match_explicit_template_command,
)
from voice_text_organizer.providers.ollama import rewrite_with_ollama
from voice_text_organizer.providers.siliconflow import rewrite_with_siliconflow
from voice_text_organizer.rewrite import build_template_prompt, postprocess_rewrite_output
from voice_text_organizer.runtime_paths import (
    RUNTIME_BACKEND_LOG_PATH,
    RUNTIME_BACKEND_STDERR_LOG_PATH,
    RUNTIME_BACKEND_STDOUT_LOG_PATH,
    RUNTIME_HISTORY_DB_PATH,
    RUNTIME_SETTINGS_PATH,
)
from voice_text_organizer.router import route_rewrite
from voice_text_organizer.template_classifier import classify_template
from voice_text_organizer.schemas import (
    AppVersionResponse,
    StartSessionRequest,
    StartSessionResponse,
    SettingsUpdateRequest,
    SettingsViewResponse,
    DashboardSummaryResponse,
    DashboardTermsExportResponse,
    DashboardTermAddRequest,
    DashboardTermAddResponse,
    DashboardTermDeleteRequest,
    DashboardTermDeleteResponse,
    StopRecordRequest,
    StopRecordResponse,
    StopSessionRequest,
    StopSessionResponse,
)
from voice_text_organizer.session_store import SessionStore
from voice_text_organizer.version import CURRENT_VERSION
from voice_text_organizer.version_check import resolve_version

LEGACY_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"
logger = logging.getLogger(__name__)
DEFAULT_AUTO_TEMPLATE_CONFIDENCE_THRESHOLD = 0.72


def _migrate_legacy_runtime_files() -> None:
    RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    candidates = [
        (LEGACY_RUNTIME_DIR / "settings.json", RUNTIME_SETTINGS_PATH),
        (LEGACY_RUNTIME_DIR / "history.db", RUNTIME_HISTORY_DB_PATH),
        (LEGACY_RUNTIME_DIR / "backend.log", RUNTIME_BACKEND_LOG_PATH),
        (LEGACY_RUNTIME_DIR / "backend.stdout.log", RUNTIME_BACKEND_STDOUT_LOG_PATH),
        (LEGACY_RUNTIME_DIR / "backend.stderr.log", RUNTIME_BACKEND_STDERR_LOG_PATH),
    ]
    for legacy_path, target_path in candidates:
        if target_path.exists() or not legacy_path.exists():
            continue
        try:
            shutil.copy2(legacy_path, target_path)
        except OSError:
            continue


_migrate_legacy_runtime_files()


def _load_runtime_settings(path: Path | None = None) -> dict[str, Any]:
    settings_path = path or RUNTIME_SETTINGS_PATH
    if not settings_path.exists():
        return {}

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    result: dict[str, Any] = {}
    if payload.get("default_mode") in ("cloud", "local"):
        result["default_mode"] = payload["default_mode"]
    if payload.get("update_channel") in ("stable", "beta"):
        result["update_channel"] = payload["update_channel"]
    if "auto_template_confidence_threshold" in payload:
        value = payload["auto_template_confidence_threshold"]
        if isinstance(value, (int, float)):
            numeric = float(value)
            if 0.0 <= numeric <= 1.0:
                result["auto_template_confidence_threshold"] = numeric
    if "siliconflow_api_key" in payload:
        value = payload["siliconflow_api_key"]
        if value is None:
            result["siliconflow_api_key"] = None
        elif isinstance(value, str):
            cleaned = value.strip()
            result["siliconflow_api_key"] = cleaned or None
    if isinstance(payload.get("last_update_check_at"), str):
        result["last_update_check_at"] = payload["last_update_check_at"]
    if isinstance(payload.get("last_release_version"), str):
        result["last_release_version"] = payload["last_release_version"]
    if isinstance(payload.get("last_release_url"), str):
        result["last_release_url"] = payload["last_release_url"]
    return result


def _save_runtime_settings(payload: dict[str, Any], path: Path | None = None) -> None:
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
        update_channel=settings.update_channel,
        auto_template_confidence_threshold=settings.auto_template_confidence_threshold,
        api_key_configured=bool(settings.siliconflow_api_key),
        api_key_masked=_mask_api_key(settings.siliconflow_api_key),
    )


def _persist_current_settings(extra_runtime_fields: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {
        "default_mode": settings.default_mode,
        "update_channel": settings.update_channel,
        "auto_template_confidence_threshold": settings.auto_template_confidence_threshold,
        "siliconflow_api_key": settings.siliconflow_api_key,
    }
    if extra_runtime_fields:
        payload.update(extra_runtime_fields)
    _save_runtime_settings(payload)


def _load_settings() -> Settings:
    default_mode = os.getenv("VTO_DEFAULT_MODE", "cloud")
    update_channel = os.getenv("VTO_UPDATE_CHANNEL", "stable")
    try:
        current = Settings(default_mode=default_mode, update_channel=update_channel)
    except ValueError:
        current = Settings(default_mode="local", update_channel="stable")

    runtime_overrides = _load_runtime_settings()
    if runtime_overrides.get("default_mode") in ("cloud", "local"):
        current.default_mode = runtime_overrides["default_mode"]  # type: ignore[assignment]
    if runtime_overrides.get("update_channel") in ("stable", "beta"):
        current.update_channel = runtime_overrides["update_channel"]  # type: ignore[assignment]
    if "auto_template_confidence_threshold" in runtime_overrides:
        current.auto_template_confidence_threshold = float(  # type: ignore[assignment]
            runtime_overrides["auto_template_confidence_threshold"]
        )
    if "siliconflow_api_key" in runtime_overrides:
        current.siliconflow_api_key = runtime_overrides["siliconflow_api_key"]
    return current


settings = _load_settings()
store = SessionStore()
recorder = AudioRecorder()
history_store = HistoryStore(RUNTIME_HISTORY_DB_PATH)


def cloud_provider(messages: list[dict[str, str]]) -> str:
    return rewrite_with_siliconflow(messages, settings=settings)


def local_provider(messages: list[dict[str, str]]) -> str:
    return rewrite_with_ollama(messages, settings=settings)


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


def _wav_duration_seconds(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as wav_file:
            framerate = wav_file.getframerate()
            frames = wav_file.getnframes()
            if framerate <= 0:
                return 0
            return max(0, round(frames / float(framerate)))
    except Exception:
        return 0


def _current_template_threshold() -> float:
    threshold = settings.auto_template_confidence_threshold
    try:
        value = float(threshold)
    except (TypeError, ValueError):
        return DEFAULT_AUTO_TEMPLATE_CONFIDENCE_THRESHOLD
    if value < 0.0 or value > 1.0:
        return DEFAULT_AUTO_TEMPLATE_CONFIDENCE_THRESHOLD
    return value


def _decide_template(
    voice_text: str,
    *,
    selected_text: str | None,
    existing_text: str | None,
) -> TemplateDecision:
    if (selected_text or "").strip() and is_whitelist_translation_command(voice_text):
        return TemplateDecision(
            template="translation",
            decision_type="selected_translation_rewrite",
            confidence=1.0,
            reason="selected_text_translation_command",
        )

    explicit_template = match_explicit_template_command(voice_text)
    if explicit_template is not None:
        return TemplateDecision(
            template=explicit_template,
            decision_type="explicit_template",
            confidence=1.0,
            reason="explicit_template_command",
        )

    classification = classify_template(
        voice_text,
        selected_text=selected_text,
        existing_text=existing_text,
    )
    return decide_template_from_classifier(
        predicted_template=classification.template,
        confidence=classification.confidence,
        threshold=_current_template_threshold(),
        reason=classification.reason,
    )


def _log_template_decision(
    endpoint: str,
    *,
    decision_type: str,
    template: str,
    confidence: float | None,
    reason: str | None,
    fallback: bool,
) -> None:
    logger.info(
        "template_decision endpoint=%s decision_type=%s template=%s confidence=%s reason=%s fallback=%s",
        endpoint,
        decision_type,
        template,
        confidence if confidence is not None else "n/a",
        reason or "n/a",
        "true" if fallback else "false",
    )


def _resolve_final_text(
    *,
    endpoint: str,
    voice_text: str,
    selected_text: str | None,
    existing_text: str | None,
    mode: str | None,
) -> str:
    decision = _decide_template(
        voice_text,
        selected_text=selected_text,
        existing_text=existing_text,
    )

    active_decision_type = decision.decision_type
    active_template = decision.template
    fallback = False

    if decision.template == "light_edit":
        final_text = postprocess_rewrite_output(voice_text)
    else:
        try:
            messages = build_template_prompt(
                voice_text,
                template=decision.template,
                selected_text=selected_text,
                existing_text=existing_text,
            )
            rewritten_text = route_rewrite(
                messages,
                cloud_fn=cloud_provider,
                local_fn=local_provider,
                default_mode=mode or settings.default_mode,
                fallback=settings.fallback_to_local_on_cloud_error,
            )
            final_text = postprocess_rewrite_output(rewritten_text)
        except Exception:
            fallback = True
            active_decision_type = "template_error_fallback_light"
            active_template = "light_edit"
            logger.warning(
                "template_fallback endpoint=%s stage=rewrite template=%s decision_type=%s",
                endpoint,
                decision.template,
                decision.decision_type,
                exc_info=True,
            )
            final_text = postprocess_rewrite_output(voice_text)

    _log_template_decision(
        endpoint,
        decision_type=active_decision_type,
        template=active_template,
        confidence=decision.confidence,
        reason=decision.reason,
        fallback=fallback,
    )
    return final_text


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

    if payload.update_channel is not None:
        settings.update_channel = payload.update_channel

    if payload.auto_template_confidence_threshold is not None:
        settings.auto_template_confidence_threshold = payload.auto_template_confidence_threshold

    if payload.api_key is not None:
        cleaned = payload.api_key.strip()
        settings.siliconflow_api_key = cleaned or None

    try:
        current_runtime = _load_runtime_settings()
        cache_fields = {
            "last_update_check_at": current_runtime.get("last_update_check_at"),
            "last_release_version": current_runtime.get("last_release_version"),
            "last_release_url": current_runtime.get("last_release_url"),
        }
        _persist_current_settings(extra_runtime_fields=cache_fields)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to persist settings: {exc}",
        ) from exc
    return _build_settings_view()


@app.get("/v1/app/version", response_model=AppVersionResponse)
def app_version() -> AppVersionResponse:
    runtime_settings = _load_runtime_settings()
    result = resolve_version(
        current_version=CURRENT_VERSION,
        runtime_settings=runtime_settings,
    )

    try:
        _persist_current_settings(extra_runtime_fields=result.cache_payload)
    except OSError:
        # Degrade gracefully on cache persistence failures.
        pass

    return AppVersionResponse(
        current_version=result.current_version,
        latest_version=result.latest_version,
        has_update=result.has_update,
        release_url=result.release_url,
        checked_at=result.checked_at,
    )


@app.get("/v1/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary() -> DashboardSummaryResponse:
    summary = history_store.get_summary()
    return DashboardSummaryResponse(**summary)


@app.get("/v1/dashboard/terms/export", response_model=DashboardTermsExportResponse)
def dashboard_terms_export(
    query: str = "",
    filter_mode: str = "all",
    min_auto_count: int = 3,
    limit: int = 300,
) -> DashboardTermsExportResponse:
    return DashboardTermsExportResponse(
        terms_blob=history_store.export_terms_blob(
            query=query,
            filter_mode=filter_mode,
            min_auto_count=min_auto_count,
            limit=limit,
        )
    )


@app.post("/v1/dashboard/terms/manual", response_model=DashboardTermAddResponse)
def dashboard_add_manual_term(payload: DashboardTermAddRequest) -> DashboardTermAddResponse:
    term = payload.term.strip()
    if not term:
        raise HTTPException(status_code=422, detail="term is empty")
    history_store.add_manual_term(term)
    return DashboardTermAddResponse(ok=True)


@app.post("/v1/dashboard/terms/delete", response_model=DashboardTermDeleteResponse)
def dashboard_delete_term(payload: DashboardTermDeleteRequest) -> DashboardTermDeleteResponse:
    term = payload.term.strip()
    if not term:
        raise HTTPException(status_code=422, detail="term is empty")
    deleted = history_store.delete_term(term)
    return DashboardTermDeleteResponse(ok=True, deleted=deleted)


@app.post("/v1/session/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest) -> StartSessionResponse:
    session_id = store.create(
        selected_text=payload.selected_text,
        existing_text=payload.existing_text,
    )
    return StartSessionResponse(session_id=session_id)


@app.post("/v1/record/start", response_model=StartSessionResponse)
def start_record(payload: StartSessionRequest) -> StartSessionResponse:
    session_id = store.create(
        selected_text=payload.selected_text,
        existing_text=payload.existing_text,
    )
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

    final_text = _resolve_final_text(
        endpoint="session_stop",
        voice_text=voice_text,
        selected_text=session.selected_text,
        existing_text=session.existing_text,
        mode=payload.mode,
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
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="recording session not found or already stopped",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to stop recording: {exc}") from exc

    try:
        voice_text = normalize_asr_text(
            transcribe_audio(audio_path, language_hint=payload.language_hint)
        )
        if not voice_text:
            raise HTTPException(status_code=422, detail="no speech detected")

        final_text = _resolve_final_text(
            endpoint="record_stop",
            voice_text=voice_text,
            selected_text=session.selected_text,
            existing_text=session.existing_text,
            mode=payload.mode,
        )
        history_store.record_transcript(
            mode=payload.mode or settings.default_mode,
            voice_text=voice_text,
            final_text=final_text,
            duration_seconds=_wav_duration_seconds(audio_path),
        )
        return StopRecordResponse(voice_text=voice_text, final_text=final_text)
    finally:
        _safe_unlink(audio_path)
