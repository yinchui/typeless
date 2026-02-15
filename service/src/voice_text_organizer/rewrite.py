from __future__ import annotations

SYSTEM_RULES = (
    "Rewrite the input into concise, logical text. "
    "Remove filler words and redundancy, preserve intent, and do not add facts."
)


def build_prompt(voice_text: str, selected_text: str | None = None) -> str:
    if selected_text:
        return (
            f"{SYSTEM_RULES}\n"
            "Selected text to refine:\n"
            f"{selected_text}\n\n"
            "New voice instruction:\n"
            f"{voice_text}"
        )
    return f"{SYSTEM_RULES}\nVoice text:\n{voice_text}"
