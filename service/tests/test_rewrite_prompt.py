from voice_text_organizer.rewrite import (
    build_prompt,
    detect_semantic_blocks,
    postprocess_rewrite_output,
)


def test_build_prompt_includes_selected_context() -> None:
    prompt = build_prompt("new voice", selected_text="old sentence")

    assert "old sentence" in prompt
    assert "new voice" in prompt
    assert "do not add facts" in prompt.lower()


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
    prompt = build_prompt(
        "先做A再做B，另外C也要跟上，最后给我结果。",
        selected_text=None,
    )

    assert "semantic blocks" in prompt.lower()
    assert "paragraph" in prompt.lower()
    assert "bullet" in prompt.lower()


def test_postprocess_adds_structure_for_single_long_line() -> None:
    raw = "先确定目标，然后拆成任务，另外安排负责人，最后今天下班前同步结果。"

    cleaned = postprocess_rewrite_output(raw)

    assert "\n" in cleaned
    assert ("- " in cleaned) or ("\n\n" in cleaned)
