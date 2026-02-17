from __future__ import annotations

import re
from typing import Literal

DecisionMode = Literal["transcribe_only", "selected_whitelist_rewrite"]

_EDGE_PUNCT_RE = re.compile(r"^[\s\.,!?;:'\"`，。！？；：、“”‘’()（）\[\]【】]+|[\s\.,!?;:'\"`，。！？；：、“”‘’()（）\[\]【】]+$")
_MULTI_SPACE_RE = re.compile(r"\s+")

_TRANSLATION_WHITELIST = {
    "翻译成中文",
    "翻成中文",
    "译成中文",
    "英译中",
    "翻译成英文",
    "翻成英文",
    "译成英文",
    "中译英",
    "translate to chinese",
    "translate to english",
}

_POLITE_PREFIXES = [
    "请帮我",
    "请你",
    "请",
    "帮我",
    "麻烦你",
    "麻烦",
    "请问",
    "please",
    "pls",
    "plz",
    "could you",
    "can you",
    "would you",
    "help me",
]

_POLITE_SUFFIXES = [
    "谢谢你",
    "谢谢",
    "thanks",
    "thank you",
]


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


def is_whitelist_translation_command(voice_text: str) -> bool:
    normalized = _normalize_command(voice_text)
    if not normalized:
        return False

    core = _strip_polite_wrappers(normalized)
    return core in _TRANSLATION_WHITELIST


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

