from voice_text_organizer.rewrite import (
    build_prompt,
    detect_semantic_blocks,
    postprocess_rewrite_output,
)


def test_build_prompt_includes_selected_context() -> None:
    messages = build_prompt("new voice", selected_text="old sentence")
    user_content = messages[1]["content"]

    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "old sentence" in user_content
    assert "new voice" in user_content
    assert "do not add facts" in messages[0]["content"].lower()


def test_detect_semantic_blocks_splits_topics() -> None:
    text = (
        "今天先确定发布范围，然后整理测试清单。"
        "另外，和设计确认首页文案。"
        "最后，晚上给我一个进度更新。"
    )

    blocks = detect_semantic_blocks(text)

    assert len(blocks) >= 2
    assert any("另外" in block for block in blocks)
    assert any("最后" in block for block in blocks)


def test_build_prompt_includes_structure_requirements() -> None:
    messages = build_prompt(
        "先做A再做B，另外C也要跟上，最后给我结果。",
        selected_text=None,
    )
    user_content = messages[1]["content"]

    assert "organize this spoken text" in user_content.lower()
    assert "voice text" in user_content.lower()
    assert "line breaks" in messages[0]["content"].lower()
    assert "bullet points" in messages[0]["content"].lower()


def test_postprocess_adds_structure_for_single_long_line() -> None:
    raw = "先确定目标，然后拆成任务，另外安排负责人，最后今天下班前同步结果。"

    cleaned = postprocess_rewrite_output(raw)

    assert "\n" in cleaned
    assert ("- " in cleaned) or ("\n\n" in cleaned)


def test_postprocess_decodes_literal_newline_tokens() -> None:
    raw = "- 第一项\\n- 第二项\\n- 第三项"

    cleaned = postprocess_rewrite_output(raw)

    assert "\\n" not in cleaned
    assert "\n" in cleaned


def test_postprocess_removes_emoji_characters() -> None:
    raw = "Please finish this today ✅ and sync it tomorrow 🚀."

    cleaned = postprocess_rewrite_output(raw)

    assert "✅" not in cleaned
    assert "🚀" not in cleaned


def test_build_prompt_continuation_includes_existing_text() -> None:
    messages = build_prompt(
        "然后我们去吃午饭",
        existing_text="今天上午开了个会",
    )
    user_content = messages[1]["content"]

    assert "今天上午开了个会" in user_content
    assert "然后我们去吃午饭" in user_content
    assert "continuation" in user_content.lower()


def test_build_prompt_selected_text_takes_priority_over_existing_text() -> None:
    messages = build_prompt(
        "改成英文",
        selected_text="你好世界",
        existing_text="前面的内容",
    )
    user_content = messages[1]["content"]

    assert "你好世界" in user_content
    assert "前面的内容" not in user_content


def test_build_prompt_continuation_truncates_long_context() -> None:
    long_text = "这是很长的文字。" * 500
    messages = build_prompt("继续写", existing_text=long_text)
    user_content = messages[1]["content"]

    assert len(long_text) > 2000
    assert long_text not in user_content
