from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class StartSessionRequest(BaseModel):
    selected_text: str | None = None
    existing_text: str | None = None


class StartSessionResponse(BaseModel):
    session_id: str


class StopSessionRequest(BaseModel):
    session_id: str
    voice_text: str
    mode: str | None = None


class StopSessionResponse(BaseModel):
    final_text: str


class StopRecordRequest(BaseModel):
    session_id: str
    mode: str | None = None
    language_hint: str = "zh"


class StopRecordResponse(BaseModel):
    voice_text: str
    final_text: str


class DashboardSummaryResponse(BaseModel):
    transcript_count: int
    total_duration_seconds: int
    total_chars: int
    average_chars_per_minute: int
    saved_seconds: int
    profile_score: int


class DashboardTermsExportResponse(BaseModel):
    terms_blob: str


class DashboardTermAddRequest(BaseModel):
    term: str


class DashboardTermAddResponse(BaseModel):
    ok: bool = True
    term: str
    existed: bool = False
    sample_count: int = 0
    status: Literal["pending", "active"] = "pending"


class DashboardTermDeleteRequest(BaseModel):
    term: str


class DashboardTermDeleteResponse(BaseModel):
    ok: bool = True
    deleted: bool = False


class DashboardTermSampleStartRequest(BaseModel):
    term: str


class DashboardTermSampleStartResponse(BaseModel):
    session_id: str


class DashboardTermSampleStopRequest(BaseModel):
    term: str
    session_id: str


class DashboardTermSampleStopResponse(BaseModel):
    ok: bool = True
    sample_id: int
    sample_count: int
    status: Literal["pending", "active"]
    duration_ms: int
    quality_score: float
    sample_path: str


class DashboardTermSamplesExportResponse(BaseModel):
    samples_blob: str


class DashboardTermSamplesExportRequest(BaseModel):
    term: str


class DashboardTermSampleDeleteRequest(BaseModel):
    term: str
    sample_id: int


class DashboardTermSampleDeleteResponse(BaseModel):
    ok: bool = True
    sample_count: int
    status: Literal["pending", "active"]


class SettingsViewResponse(BaseModel):
    default_mode: Literal["cloud", "local"]
    update_channel: Literal["stable", "beta"] = "stable"
    auto_template_confidence_threshold: float
    personalized_acoustic_enabled: bool
    api_key_configured: bool
    api_key_masked: str | None = None


class SettingsUpdateRequest(BaseModel):
    default_mode: Literal["cloud", "local"] | None = None
    update_channel: Literal["stable", "beta"] | None = None
    auto_template_confidence_threshold: float | None = None
    personalized_acoustic_enabled: bool | None = None
    api_key: str | None = None


class AppVersionResponse(BaseModel):
    current_version: str
    latest_version: str
    has_update: bool
    release_url: str
    checked_at: str
