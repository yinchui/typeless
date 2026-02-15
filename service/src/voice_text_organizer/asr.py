from __future__ import annotations

from pathlib import Path

import httpx

from voice_text_organizer.config import Settings


def normalize_asr_text(text: str) -> str:
    return " ".join(text.strip().split())


def transcribe_with_siliconflow(
    audio_path: str | Path,
    settings: Settings,
    language: str = "auto",
) -> str:
    if not settings.siliconflow_api_key:
        raise ValueError("Missing SILICONFLOW_API_KEY")

    path = Path(audio_path)
    data: dict[str, str] = {"model": settings.siliconflow_asr_model}
    if language != "auto":
        data["language"] = language

    with path.open("rb") as audio_file:
        response = httpx.post(
            settings.siliconflow_asr_url,
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
            data=data,
            files={"file": (path.name, audio_file, "audio/wav")},
            timeout=60.0,
        )
    response.raise_for_status()
    payload = response.json()
    return normalize_asr_text(payload.get("text", ""))
