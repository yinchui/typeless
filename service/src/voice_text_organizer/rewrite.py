from __future__ import annotations

import re
from typing import Literal

TemplatePrompt = Literal["light_edit", "meeting_minutes", "task_list", "translation"]

BASE_SYSTEM_RULES = (
    "You are a language organizer. "
    "Rewrite spoken input into clear, structured text. "
    "Remove filler words and redundancy, preserve intent and details, "
    "and do not add facts. "
    "Keep the same language as the input unless translation is requested. "
    "Use real line breaks for paragraph separation. "
    "Use bullet points when listing multiple items or steps."
)
MAX_EXISTING_TEXT_CHARS = 2000

TOPIC_MARKER_RE = re.compile(
    r"^(?:"
    r"another|also|next|then|finally|first|second|third|"
    r"\u53e6\u5916|\u6b64\u5916|\u540c\u65f6|\u7136\u540e|\u6700\u540e|"
    r"\u5176\u6b21|\u4e0d\u8fc7|\u4f46\u662f|\u53e6\u4e00\u65b9\u9762|"
    r"\u7b2c\u4e00|\u7b2c\u4e8c|\u7b2c\u4e09"
    r")\b",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")
TOPIC_COMMA_SPLIT_RE = re.compile(
    r"[\uff0c,](?=\s*(?:"
    r"another|also|next|then|finally|first|second|third|"
    r"\u53e6\u5916|\u6b64\u5916|\u540c\u65f6|\u7136\u540e|\u6700\u540e|"
    r"\u5176\u6b21|\u4e0d\u8fc7|\u4f46\u662f|\u53e6\u4e00\u65b9\u9762|"
    r"\u7b2c\u4e00|\u7b2c\u4e8c|\u7b2c\u4e09"
    r"))",
    re.IGNORECASE,
)
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]",
    re.UNICODE,
)


def strip_emoji(text: str) -> str:
    text = EMOJI_RE.sub("", text)
    text = text.replace("\uFE0F", "")
    text = text.replace("\u200D", "")
    return text


def _normalize_whitespace(text: str) -> str:
    text = strip_emoji(text)
    text = text.replace("\\r\\n", "\n")
    text = text.replace("\\n", "\n")
    text = text.replace("\\r", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[\u3002\uff01\uff1f\uff1b.!?;])\s*", text.strip())
    return [part.strip() for part in parts if part.strip()]


def detect_semantic_blocks(text: str) -> list[str]:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return []

    blocks: list[str] = []
    for paragraph in normalized.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        pieces = [piece.strip() for piece in TOPIC_COMMA_SPLIT_RE.split(paragraph) if piece.strip()]
        for piece in pieces:
            sentences = _split_sentences(piece)
            if not sentences:
                continue

            current: list[str] = []
            for sentence in sentences:
                if current and TOPIC_MARKER_RE.match(sentence):
                    blocks.append(" ".join(current).strip())
                    current = [sentence]
                else:
                    current.append(sentence)
            if current:
                blocks.append(" ".join(current).strip())

    return blocks or [normalized]


def _format_semantic_blocks(blocks: list[str]) -> str:
    if not blocks:
        return "- (none)"
    return "\n".join(f"{index}. {block}" for index, block in enumerate(blocks, start=1))


def _should_use_bullets(block: str, sentences: list[str]) -> bool:
    if len(sentences) >= 3:
        return True
    if len(sentences) >= 2 and re.search(
        r"(?:\band\b|\bor\b|also|then|finally|next|"
        r"\u53e6\u5916|\u540c\u65f6|\u7136\u540e|\u6700\u540e|\u4ee5\u53ca|\u5e76\u4e14|\u6216\u8005)",
        block,
        re.IGNORECASE,
    ):
        return True
    return False


def postprocess_rewrite_output(text: str) -> str:
    cleaned = _normalize_whitespace(text)
    if not cleaned:
        return cleaned

    has_structure = ("\n\n" in cleaned) or any(
        BULLET_RE.match(line) for line in cleaned.splitlines() if line.strip()
    )
    if has_structure:
        return cleaned

    blocks = detect_semantic_blocks(cleaned)
    if len(blocks) == 1:
        only_block = blocks[0]
        sentences = _split_sentences(only_block)
        if _should_use_bullets(only_block, sentences):
            return "\n".join(f"- {sentence}" for sentence in sentences)
        return cleaned

    lines: list[str] = []
    for block in blocks:
        sentences = _split_sentences(block)
        if _should_use_bullets(block, sentences):
            lines.extend(f"- {sentence}" for sentence in sentences)
        else:
            lines.append(block)
        lines.append("")
    return "\n".join(lines).strip()


def _truncate_existing_text(text: str) -> str:
    if len(text) <= MAX_EXISTING_TEXT_CHARS:
        return text
    return "..." + text[-MAX_EXISTING_TEXT_CHARS:]


def _template_instruction(template: TemplatePrompt) -> str:
    if template == "meeting_minutes":
        return (
            "Format as meeting minutes using sections when present: "
            "Topic, Key Discussion, Decisions, Action Items. "
            "Omit any missing sections and never invent facts."
        )
    if template == "task_list":
        return (
            "Format as an actionable task list. "
            "Each item should prefer action, object, owner (if present), and deadline (if present). "
            "Leave unknown fields blank instead of guessing."
        )
    if template == "translation":
        return (
            "Translation only. "
            "Keep terminology, numbers, and list structure when possible. "
            "Do not summarize or expand."
        )
    return (
        "Produce a light edit with readable paragraphs and punctuation fixes. "
        "Do not force rigid section templates."
    )


def build_template_prompt(
    voice_text: str,
    *,
    template: TemplatePrompt,
    selected_text: str | None = None,
    existing_text: str | None = None,
) -> list[dict[str, str]]:
    system_msg = {"role": "system", "content": f"{BASE_SYSTEM_RULES} {_template_instruction(template)}"}

    if template == "translation" and selected_text:
        user_content = (
            f"Selected text:\n{selected_text}\n\n"
            f"Voice instruction:\n{voice_text}\n\n"
            "Translate the selected text according to the voice instruction. "
            "Return only the translated text."
        )
    elif selected_text:
        user_content = (
            f"Selected text to refine:\n{selected_text}\n\n"
            f"Voice instruction:\n{voice_text}\n\n"
            f"Apply template '{template}' to the selected text. "
            "Return only the final text."
        )
    elif existing_text:
        truncated = _truncate_existing_text(existing_text)
        user_content = (
            f"The user has already written:\n---\n{truncated}\n---\n\n"
            f"The user then spoke to continue:\n{voice_text}\n\n"
            f"Apply template '{template}' to produce ONLY the new continuation text. "
            "Do NOT repeat existing text."
        )
    elif template == "meeting_minutes":
        user_content = (
            f"Voice text:\n{voice_text}\n\n"
            "Organize this spoken text as meeting minutes with sections: "
            "Topic, Key Discussion, Decisions, Action Items. "
            "Omit sections that are not present. Return only the final text."
        )
    elif template == "task_list":
        user_content = (
            f"Voice text:\n{voice_text}\n\n"
            "Organize this spoken text into an actionable task list. "
            "Return only the final text."
        )
    elif template == "translation":
        user_content = (
            f"Voice text:\n{voice_text}\n\n"
            "Translate this content as instructed by the user. "
            "Return only the translated text."
        )
    else:
        user_content = (
            f"Voice text:\n{voice_text}\n\n"
            "Organize this spoken text into clear, structured written text. "
            "Return only the final organized text."
        )

    return [system_msg, {"role": "user", "content": user_content}]


def build_prompt(
    voice_text: str,
    selected_text: str | None = None,
    existing_text: str | None = None,
) -> list[dict[str, str]]:
    return build_template_prompt(
        voice_text,
        template="light_edit",
        selected_text=selected_text,
        existing_text=existing_text,
    )
