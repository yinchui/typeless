from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import wave
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import numpy as np

from fastapi import FastAPI, HTTPException

from voice_text_organizer.asr import normalize_asr_text, transcribe_with_siliconflow
from voice_text_organizer.audio import AudioRecorder
from voice_text_organizer.config import Settings
from voice_text_organizer.history_store import DEFAULT_PROFILE_ID, HistoryStore
from voice_text_organizer.personalization import (
    build_mfcc_fingerprint_bytes,
    enhance_voice_text,
)
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
    RUNTIME_DIR,
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
    DashboardTermSampleDeleteRequest,
    DashboardTermSampleDeleteResponse,
    DashboardTermSampleStartRequest,
    DashboardTermSampleStartResponse,
    DashboardTermSamplesExportRequest,
    DashboardTermSamplesExportResponse,
    DashboardTermSampleStopRequest,
    DashboardTermSampleStopResponse,
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
_CJK_CHAR_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
MAX_TERM_LENGTH = 20
MAX_SAMPLE_DURATION_MS = 15000
MIN_SAMPLE_DURATION_MS = 300
MAX_SAMPLE_SILENCE_RATIO = 0.97
MIN_SAMPLE_RMS = 0.003
MIN_SAMPLE_PEAK = 0.01
MIN_SILENCE_ABS_THRESHOLD = 0.003
MAX_SILENCE_ABS_THRESHOLD = 0.015
SILENCE_THRESHOLD_RMS_SCALE = 1.2
MIN_ENERGY_RATIO_FOR_SILENCE_REJECT = 1.5
MIN_PEAK_RATIO_FOR_SILENCE_REJECT = 1.3
MAX_SAMPLE_CLIPPING_RATIO = 0.03
PERSONALIZATION_TIMEOUT_MS = 900


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
    if isinstance(payload.get("personalized_acoustic_enabled"), bool):
        result["personalized_acoustic_enabled"] = payload["personalized_acoustic_enabled"]
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
        personalized_acoustic_enabled=settings.personalized_acoustic_enabled,
        api_key_configured=bool(settings.siliconflow_api_key),
        api_key_masked=_mask_api_key(settings.siliconflow_api_key),
    )


def _persist_current_settings(extra_runtime_fields: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {
        "default_mode": settings.default_mode,
        "update_channel": settings.update_channel,
        "auto_template_confidence_threshold": settings.auto_template_confidence_threshold,
        "personalized_acoustic_enabled": settings.personalized_acoustic_enabled,
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
    if "personalized_acoustic_enabled" in runtime_overrides:
        current.personalized_acoustic_enabled = bool(  # type: ignore[assignment]
            runtime_overrides["personalized_acoustic_enabled"]
        )
    if "siliconflow_api_key" in runtime_overrides:
        current.siliconflow_api_key = runtime_overrides["siliconflow_api_key"]
    return current


settings = _load_settings()
store = SessionStore()
recorder = AudioRecorder()
history_store = HistoryStore(RUNTIME_HISTORY_DB_PATH)
sample_recording_sessions: dict[str, str] = {}
sample_recording_lock = Lock()


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


def _validate_term_or_raise(raw_term: str) -> str:
    term = raw_term.strip()
    if not term:
        raise HTTPException(status_code=422, detail="term is empty")
    if len(term) > MAX_TERM_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"term exceeds max length {MAX_TERM_LENGTH}",
        )
    return term


def _term_sample_dir(term: str) -> Path:
    runtime_dir_env = os.getenv("VTO_RUNTIME_DIR")
    if runtime_dir_env:
        base_dir = Path(runtime_dir_env).expanduser().resolve().parent
    else:
        base_dir = RUNTIME_DIR.parent
    term_hash = hashlib.sha1(term.encode("utf-8")).hexdigest()[:16]
    return base_dir / "recordings" / "term_samples" / DEFAULT_PROFILE_ID / term_hash


def _fallback_term_sample_dir(term: str) -> Path:
    term_hash = hashlib.sha1(term.encode("utf-8")).hexdigest()[:16]
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data) / "Typeless"
    else:
        base_dir = RUNTIME_DIR
    return base_dir / "recordings_fallback" / "term_samples" / DEFAULT_PROFILE_ID / term_hash


def _persist_term_sample_file(term: str, session_id: str, source_path: Path) -> Path:
    target_dirs = [_term_sample_dir(term), _fallback_term_sample_dir(term)]
    last_error: OSError | None = None
    for sample_dir in target_dirs:
        try:
            sample_dir.mkdir(parents=True, exist_ok=True)
            target_path = sample_dir / f"{session_id}.wav"
            shutil.copy2(source_path, target_path)
            return target_path
        except OSError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise OSError("failed to persist term sample")


def _evaluate_sample_audio_quality(audio_path: Path) -> dict[str, float]:
    with wave.open(str(audio_path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        raw_audio = wav_file.readframes(frame_count)

    if sample_width != 2:
        raise ValueError("unsupported sample format")
    if sample_rate <= 0:
        raise ValueError("invalid sample rate")

    pcm = np.frombuffer(raw_audio, dtype=np.int16)
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1).astype(np.int16)
    if pcm.size == 0:
        raise ValueError("empty audio")

    duration_ms = int(round((pcm.size / float(sample_rate)) * 1000.0))
    if duration_ms <= MIN_SAMPLE_DURATION_MS:
        raise ValueError("sample duration must be > 0.3s")
    if duration_ms > MAX_SAMPLE_DURATION_MS:
        raise ValueError("sample duration must be <= 15s")

    normalized = pcm.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(np.square(normalized))))
    peak = float(np.max(np.abs(normalized)))
    if rms < MIN_SAMPLE_RMS and peak < MIN_SAMPLE_PEAK:
        raise ValueError("sample volume too low")

    silence_threshold = min(
        MAX_SILENCE_ABS_THRESHOLD,
        max(MIN_SILENCE_ABS_THRESHOLD, rms * SILENCE_THRESHOLD_RMS_SCALE),
    )
    silence_ratio = float(np.mean(np.abs(normalized) < silence_threshold))
    if (
        silence_ratio >= MAX_SAMPLE_SILENCE_RATIO
        and rms < (MIN_SAMPLE_RMS * MIN_ENERGY_RATIO_FOR_SILENCE_REJECT)
        and peak < (MIN_SAMPLE_PEAK * MIN_PEAK_RATIO_FOR_SILENCE_REJECT)
    ):
        raise ValueError("too much silence in sample")

    clipping_ratio = float(np.mean(np.abs(pcm) >= 32760))
    if clipping_ratio > MAX_SAMPLE_CLIPPING_RATIO:
        raise ValueError("sample clipping is too high")

    quality_score = max(
        0.0,
        min(
            1.0,
            1.0
            - (silence_ratio * 0.45)
            - (max(0.0, MIN_SAMPLE_RMS - rms) * 4.0)
            - (clipping_ratio * 1.2),
        ),
    )
    return {
        "duration_ms": float(duration_ms),
        "quality_score": float(quality_score),
        "silence_ratio": float(silence_ratio),
        "peak": float(peak),
        "rms": float(rms),
        "clipping_ratio": float(clipping_ratio),
    }


def _apply_personalized_acoustic(voice_text: str, audio_path: Path) -> str:
    try:
        active = history_store.get_active_terms(profile_id=DEFAULT_PROFILE_ID, limit=200)
        if not active:
            return voice_text

        active_terms = [str(item["term"]) for item in active]
        sample_lookup = history_store.load_term_sample_fingerprints(
            active_terms,
            profile_id=DEFAULT_PROFILE_ID,
        )
        return enhance_voice_text(
            voice_text=voice_text,
            audio_path=audio_path,
            active_terms=active_terms,
            sample_lookup=sample_lookup,
            timeout_ms=PERSONALIZATION_TIMEOUT_MS,
        )
    except Exception:
        logger.warning("personalized_acoustic_fallback_to_asr_text", exc_info=True)
        return voice_text


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


def _is_language_drift_to_english(source_text: str, rewritten_text: str) -> bool:
    source_cjk = len(_CJK_CHAR_RE.findall(source_text))
    source_latin = len(_LATIN_CHAR_RE.findall(source_text))
    rewritten_cjk = len(_CJK_CHAR_RE.findall(rewritten_text))
    rewritten_latin = len(_LATIN_CHAR_RE.findall(rewritten_text))

    source_is_chinese_primary = source_cjk >= 4 and source_cjk >= source_latin
    rewritten_is_english_primary = rewritten_latin >= 12 and rewritten_latin >= (rewritten_cjk * 4)
    return source_is_chinese_primary and rewritten_is_english_primary


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

    has_selected_text = bool((selected_text or "").strip())
    # Keep selected-text safety: non-translation commands should not rewrite the selected content.
    if decision.template == "light_edit" and has_selected_text:
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
            if decision.template != "translation" and _is_language_drift_to_english(
                voice_text, rewritten_text
            ):
                fallback = True
                active_decision_type = "language_mismatch_fallback_light"
                active_template = "light_edit"
                logger.warning(
                    "template_fallback endpoint=%s stage=language_drift template=%s decision_type=%s",
                    endpoint,
                    decision.template,
                    decision.decision_type,
                )
                final_text = postprocess_rewrite_output(voice_text)
            else:
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

    if payload.personalized_acoustic_enabled is not None:
        settings.personalized_acoustic_enabled = payload.personalized_acoustic_enabled

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
    status: str = "all",
    limit: int = 300,
) -> DashboardTermsExportResponse:
    return DashboardTermsExportResponse(
        terms_blob=history_store.export_terms_blob(
            query=query,
            status=status,
            limit=limit,
        )
    )


@app.post("/v1/dashboard/terms/manual", response_model=DashboardTermAddResponse)
def dashboard_add_manual_term(payload: DashboardTermAddRequest) -> DashboardTermAddResponse:
    term = _validate_term_or_raise(payload.term)
    result = history_store.add_manual_term(term)
    return DashboardTermAddResponse(**result)


@app.post("/v1/dashboard/terms/delete", response_model=DashboardTermDeleteResponse)
def dashboard_delete_term(payload: DashboardTermDeleteRequest) -> DashboardTermDeleteResponse:
    term = _validate_term_or_raise(payload.term)
    deleted = history_store.delete_term(term)
    return DashboardTermDeleteResponse(ok=True, deleted=deleted)


@app.post("/v1/dashboard/terms/sample/start", response_model=DashboardTermSampleStartResponse)
def dashboard_start_term_sample(payload: DashboardTermSampleStartRequest) -> DashboardTermSampleStartResponse:
    term = _validate_term_or_raise(payload.term)
    history_store.add_manual_term(term)

    session_id = str(uuid4())
    with sample_recording_lock:
        sample_recording_sessions[session_id] = term
    try:
        recorder.start(session_id)
    except Exception as exc:
        with sample_recording_lock:
            sample_recording_sessions.pop(session_id, None)
        raise HTTPException(status_code=500, detail=f"failed to start recording: {exc}") from exc
    return DashboardTermSampleStartResponse(session_id=session_id)


@app.post("/v1/dashboard/terms/sample/stop", response_model=DashboardTermSampleStopResponse)
def dashboard_stop_term_sample(payload: DashboardTermSampleStopRequest) -> DashboardTermSampleStopResponse:
    term = _validate_term_or_raise(payload.term)
    with sample_recording_lock:
        expected_term = sample_recording_sessions.get(payload.session_id)
    if expected_term is None:
        raise HTTPException(status_code=404, detail="sample recording session not found")
    if expected_term != term:
        raise HTTPException(status_code=422, detail="term does not match recording session")

    try:
        audio_path = recorder.stop(payload.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="recording session not found or already stopped") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to stop recording: {exc}") from exc
    finally:
        with sample_recording_lock:
            sample_recording_sessions.pop(payload.session_id, None)

    saved_path: Path | None = None
    try:
        quality = _evaluate_sample_audio_quality(audio_path)
        saved_path = _persist_term_sample_file(term, payload.session_id, audio_path)
        fingerprint = build_mfcc_fingerprint_bytes(saved_path)
        result = history_store.add_term_sample(
            term=term,
            audio_path=str(saved_path),
            duration_ms=int(quality["duration_ms"]),
            quality_score=float(quality["quality_score"]),
            mfcc_fingerprint=fingerprint,
        )
        return DashboardTermSampleStopResponse(
            ok=True,
            sample_id=int(result["sample_id"]),
            sample_count=int(result["sample_count"]),
            status=result["status"],
            duration_ms=int(quality["duration_ms"]),
            quality_score=float(quality["quality_score"]),
            sample_path=str(saved_path),
        )
    except ValueError as exc:
        if saved_path is not None:
            _safe_unlink(saved_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        if saved_path is not None:
            _safe_unlink(saved_path)
        raise HTTPException(status_code=500, detail=f"failed to save term sample: {exc}") from exc
    finally:
        _safe_unlink(audio_path)


@app.get("/v1/dashboard/terms/samples/export", response_model=DashboardTermSamplesExportResponse)
def dashboard_export_term_samples(term: str) -> DashboardTermSamplesExportResponse:
    validated_term = _validate_term_or_raise(term)
    return DashboardTermSamplesExportResponse(
        samples_blob=history_store.export_term_samples_blob(validated_term)
    )


@app.post("/v1/dashboard/terms/samples/export", response_model=DashboardTermSamplesExportResponse)
def dashboard_export_term_samples_post(
    payload: DashboardTermSamplesExportRequest,
) -> DashboardTermSamplesExportResponse:
    validated_term = _validate_term_or_raise(payload.term)
    return DashboardTermSamplesExportResponse(
        samples_blob=history_store.export_term_samples_blob(validated_term)
    )


@app.post("/v1/dashboard/terms/sample/delete", response_model=DashboardTermSampleDeleteResponse)
def dashboard_delete_term_sample(payload: DashboardTermSampleDeleteRequest) -> DashboardTermSampleDeleteResponse:
    term = _validate_term_or_raise(payload.term)
    result = history_store.delete_term_sample(term, payload.sample_id)
    return DashboardTermSampleDeleteResponse(**result)


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
        if settings.personalized_acoustic_enabled:
            voice_text = _apply_personalized_acoustic(voice_text, audio_path)

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
