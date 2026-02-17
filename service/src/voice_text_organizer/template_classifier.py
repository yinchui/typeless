from __future__ import annotations

import re
from dataclasses import dataclass

from voice_text_organizer.policy import TemplateName

_MULTI_SPACE_RE = re.compile(r"\s+")
_LIST_MARKER_RE = re.compile(r"(?:^|\s)(?:\d+[.)]|[-*])\s+")

_MEETING_SIGNAL_TOKENS = (
    "\u4f1a\u8bae",
    "\u8bae\u9898",
    "\u51b3\u8bae",
    "\u7eaa\u8981",
    "meeting",
    "minutes",
)
_TASK_SIGNAL_TOKENS = (
    "\u5f85\u529e",
    "\u4efb\u52a1",
    "\u5b8c\u6210",
    "\u8ddf\u8fdb",
    "\u622a\u6b62",
    "todo",
    "task",
    "action item",
)


@dataclass(frozen=True)
class TemplateClassification:
    template: TemplateName
    confidence: float
    reason: str


def _normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    lowered = _MULTI_SPACE_RE.sub(" ", lowered)
    return lowered


def _score_hits(text: str, tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if token in text)


def _looks_structured(text: str) -> bool:
    if _LIST_MARKER_RE.search(text):
        return True
    separators = text.count("\n") + text.count(";") + text.count("\uff1b") + text.count("\uff0c")
    return separators >= 2


def classify_template(
    voice_text: str,
    *,
    selected_text: str | None = None,
    existing_text: str | None = None,
) -> TemplateClassification:
    del selected_text
    del existing_text

    normalized = _normalize_text(voice_text)
    if not normalized:
        return TemplateClassification(template="light_edit", confidence=0.0, reason="empty_input")

    meeting_score = _score_hits(normalized, _MEETING_SIGNAL_TOKENS)
    if meeting_score >= 2 and _looks_structured(normalized):
        return TemplateClassification(
            template="meeting_minutes",
            confidence=0.84,
            reason="meeting_signals_detected",
        )

    task_score = _score_hits(normalized, _TASK_SIGNAL_TOKENS)
    if task_score >= 2 or (task_score >= 1 and _looks_structured(normalized)):
        return TemplateClassification(
            template="task_list",
            confidence=0.82,
            reason="task_signals_detected",
        )

    return TemplateClassification(
        template="light_edit",
        confidence=0.60,
        reason="default_light_edit",
    )
