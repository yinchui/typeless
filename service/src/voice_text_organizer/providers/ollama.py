from __future__ import annotations

import httpx

from voice_text_organizer.config import Settings


def rewrite_with_ollama(prompt: str, settings: Settings) -> str:
    response = httpx.post(
        f"{settings.ollama_base_url}/api/generate",
        json={
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["response"].strip()
