from __future__ import annotations

import re

SYSTEM_RULES = (
    "You are a language organizer. Rewrite spoken input into clear, structured text. "
    "Remove filler words and redundancy, preserve intent and details, and do not add facts."
)

TOPIC_MARKER_RE = re.compile(
    r"^(?:"
    r"another|also|next|then|finally|first|second|third|"
    r"\u53e6\u5916|\u6b64\u5916|\u540c\u65f6|\u7136\u540e|\u6700\u540e|"
    r"\u5176\u6b21|\u4e0d\u8fc7|\u4f46\u662f|\u53e6\u4e00\u65b9\u9762|"
    r"\u7b2c\u4e00|\u7b2c\u4e8c|\u7b2c\u4e09"
    r")\b",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
TOPIC_COMMA_SPLIT_RE = re.compile(
    r"[，,](?=\s*(?:"
    r"another|also|next|then|finally|first|second|third|"
    r"\u53e6\u5916|\u6b64\u5916|\u540c\u65f6|\u7136\u540e|\u6700\u540e|"
    r"\u5176\u6b21|\u4e0d\u8fc7|\u4f46\u662f|\u53e6\u4e00\u65b9\u9762|"
    r"\u7b2c\u4e00|\u7b2c\u4e8c|\u7b2c\u4e09"
    r"))",
    re.IGNORECASE,
)


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；.!?;])\s*", text.strip())
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


def build_prompt(voice_text: str, selected_text: str | None = None) -> str:
    semantic_blocks = detect_semantic_blocks(voice_text)
    block_section = _format_semantic_blocks(semantic_blocks)

    structure_rules = (
        "Output requirements:\n"
        "- Keep the full meaning and important constraints.\n"
        "- Remove filler words and repeated fragments.\n"
        "- Use paragraph breaks when topics change.\n"
        "- Use bullet points when a paragraph contains multiple steps, conditions, or items.\n"
        "- Title is optional and usually not needed.\n"
        "- Keep the same language as the input.\n"
        "- Do not add facts."
    )

    if selected_text:
        return (
            f"{SYSTEM_RULES}\n"
            "Detected semantic blocks from voice input:\n"
            f"{block_section}\n\n"
            "Selected text to refine:\n"
            f"{selected_text}\n\n"
            "New voice instruction:\n"
            f"{voice_text}\n\n"
            f"{structure_rules}\n"
            "Return only the final organized text."
        )
    return (
        f"{SYSTEM_RULES}\n"
        "Detected semantic blocks from voice input:\n"
        f"{block_section}\n\n"
        "Voice text:\n"
        f"{voice_text}\n\n"
        f"{structure_rules}\n"
        "Return only the final organized text."
    )
