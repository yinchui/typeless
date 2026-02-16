from __future__ import annotations

import httpx

from voice_text_organizer.config import Settings


def rewrite_with_ollama(messages: list[dict[str, str]], settings: Settings) -> str:
    response = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["message"]["content"].strip()
