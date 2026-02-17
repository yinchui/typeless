from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

DecisionMode = Literal["transcribe_only", "selected_whitelist_rewrite"]
TemplateName = Literal["light_edit", "meeting_minutes", "task_list", "translation"]
DecisionType = Literal[
    "selected_translation_rewrite",
    "explicit_template",
    "auto_template",
    "low_confidence_fallback_light",
    "language_mismatch_fallback_light",
    "template_error_fallback_light",
]

_EDGE_PUNCT_RE = re.compile(
    r"^[\s\.,!?;:'\"`\u3002\uff0c\uff1f\uff01\uff1b\uff1a\u3001\u201c\u201d\u2018\u2019\(\)\[\]\u3010\u3011]+|"
    r"[\s\.,!?;:'\"`\u3002\uff0c\uff1f\uff01\uff1b\uff1a\u3001\u201c\u201d\u2018\u2019\(\)\[\]\u3010\u3011]+$"
)
_MULTI_SPACE_RE = re.compile(r"\s+")

_TRANSLATION_WHITELIST = {
    "\u7ffb\u8bd1\u6210\u4e2d\u6587",
    "\u7ffb\u6210\u4e2d\u6587",
    "\u8bd1\u6210\u4e2d\u6587",
    "\u82f1\u8bd1\u4e2d",
    "\u7ffb\u8bd1\u6210\u82f1\u6587",
    "\u7ffb\u6210\u82f1\u6587",
    "\u8bd1\u6210\u82f1\u6587",
    "\u4e2d\u8bd1\u82f1",
    "translate to chinese",
    "translate to english",
}

_POLITE_PREFIXES = [
    "\u8bf7\u5e2e\u6211",
    "\u8bf7\u4f60",
    "\u8bf7",
    "\u5e2e\u6211",
    "\u9ebb\u70e6\u4f60",
    "\u9ebb\u70e6",
    "\u8bf7\u95ee",
    "please",
    "pls",
    "plz",
    "could you",
    "can you",
    "would you",
    "help me",
]

_POLITE_SUFFIXES = [
    "\u8c22\u8c22\u4f60",
    "\u8c22\u8c22",
    "thanks",
    "thank you",
]

_ACTION_TOKENS = (
    "\u6574\u7406",
    "\u68b3\u7406",
    "\u5199\u6210",
    "\u8f93\u51fa",
    "\u751f\u6210",
    "\u5217",
    "\u6539\u6210",
    "\u8f6c\u6362",
    "\u603b\u7ed3",
    "\u5f52\u7eb3",
    "organize",
    "rewrite",
    "format",
    "convert",
    "list",
    "summarize",
    "make",
)
_MEETING_TEMPLATE_TOKENS = (
    "\u4f1a\u8bae\u7eaa\u8981",
    "\u4f1a\u8bae\u8bb0\u5f55",
    "\u7eaa\u8981",
    "meeting minutes",
    "minutes",
)
_TASK_TEMPLATE_TOKENS = (
    "\u4efb\u52a1\u6e05\u5355",
    "\u4efb\u52a1\u5217\u8868",
    "\u5f85\u529e",
    "\u6e05\u5355",
    "task list",
    "todo list",
    "to-do list",
    "action items",
)
_LIGHT_EDIT_TEMPLATE_TOKENS = (
    "\u8f7b\u5ea6\u6574\u7406",
    "\u8f7b\u6574\u7406",
    "\u6da6\u8272",
    "\u4f18\u5316\u8868\u8fbe",
    "light edit",
    "clean up",
)
_TRANSLATION_ACTION_TOKENS = ("\u7ffb\u8bd1", "translate")
_TRANSLATION_TARGET_TOKENS = (
    "\u4e2d\u6587",
    "\u6c49\u8bed",
    "\u82f1\u6587",
    "chinese",
    "english",
)


@dataclass(frozen=True)
class TemplateDecision:
    template: TemplateName
    decision_type: DecisionType
    confidence: float | None = None
    reason: str | None = None


def _trim_edge_punctuation(text: str) -> str:
    return _EDGE_PUNCT_RE.sub("", text).strip()


def _normalize_command(text: str) -> str:
    normalized = text.lower().strip()
    normalized = _trim_edge_punctuation(normalized)
    normalized = _MULTI_SPACE_RE.sub(" ", normalized)
    return normalized


def _strip_polite_wrappers(text: str) -> str:
    current = text
    while current:
        before = current
        for prefix in sorted(_POLITE_PREFIXES, key=len, reverse=True):
            if current.startswith(prefix + " "):
                current = current[len(prefix) + 1 :]
                break
            if current.startswith(prefix):
                current = current[len(prefix) :]
                break
        current = _trim_edge_punctuation(_MULTI_SPACE_RE.sub(" ", current))

        for suffix in sorted(_POLITE_SUFFIXES, key=len, reverse=True):
            if current.endswith(" " + suffix):
                current = current[: -(len(suffix) + 1)]
                break
            if current.endswith(suffix):
                current = current[: -len(suffix)]
                break
        current = _trim_edge_punctuation(_MULTI_SPACE_RE.sub(" ", current))
        if current == before:
            break
    return current


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def is_whitelist_translation_command(voice_text: str) -> bool:
    normalized = _normalize_command(voice_text)
    if not normalized:
        return False

    core = _strip_polite_wrappers(normalized)
    return core in _TRANSLATION_WHITELIST


def match_explicit_template_command(voice_text: str) -> TemplateName | None:
    normalized = _normalize_command(voice_text)
    if not normalized:
        return None
    core = _strip_polite_wrappers(normalized)
    if not core:
        return None

    if _contains_any(core, _TRANSLATION_ACTION_TOKENS) and _contains_any(core, _TRANSLATION_TARGET_TOKENS):
        return "translation"
    if _contains_any(core, _ACTION_TOKENS) and _contains_any(core, _MEETING_TEMPLATE_TOKENS):
        return "meeting_minutes"
    if _contains_any(core, _ACTION_TOKENS) and _contains_any(core, _TASK_TEMPLATE_TOKENS):
        return "task_list"
    if _contains_any(core, _ACTION_TOKENS) and _contains_any(core, _LIGHT_EDIT_TEMPLATE_TOKENS):
        return "light_edit"
    return None


def decide_template_from_classifier(
    *,
    predicted_template: TemplateName,
    confidence: float,
    threshold: float,
    reason: str | None = None,
) -> TemplateDecision:
    if confidence < threshold:
        return TemplateDecision(
            template="light_edit",
            decision_type="low_confidence_fallback_light",
            confidence=confidence,
            reason=reason,
        )
    return TemplateDecision(
        template=predicted_template,
        decision_type="auto_template",
        confidence=confidence,
        reason=reason,
    )


def decide_processing_mode(
    voice_text: str,
    *,
    selected_text: str | None,
    existing_text: str | None,
) -> DecisionMode:
    del existing_text  # policy v1 ignores full-context content
    if not (selected_text or "").strip():
        return "transcribe_only"

    if is_whitelist_translation_command(voice_text):
        return "selected_whitelist_rewrite"
    return "transcribe_only"
