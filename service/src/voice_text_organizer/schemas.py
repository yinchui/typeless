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
    language_hint: str = "auto"


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


class DashboardTermDeleteRequest(BaseModel):
    term: str


class DashboardTermDeleteResponse(BaseModel):
    ok: bool = True
    deleted: bool = False


class SettingsViewResponse(BaseModel):
    default_mode: Literal["cloud", "local"]
    api_key_configured: bool
    api_key_masked: str | None = None


class SettingsUpdateRequest(BaseModel):
    default_mode: Literal["cloud", "local"] | None = None
    api_key: str | None = None
