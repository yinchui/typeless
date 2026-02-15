from __future__ import annotations

import httpx

from voice_text_organizer.config import Settings


def rewrite_with_siliconflow(prompt: str, settings: Settings) -> str:
    if not settings.siliconflow_api_key:
        raise ValueError("Missing SILICONFLOW_API_KEY")

    response = httpx.post(
        settings.siliconflow_base_url,
        headers={
            "Authorization": f"Bearer {settings.siliconflow_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.siliconflow_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()
