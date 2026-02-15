from voice_text_organizer.rewrite import build_prompt


def test_build_prompt_includes_selected_context() -> None:
    prompt = build_prompt("new voice", selected_text="old sentence")

    assert "old sentence" in prompt
    assert "new voice" in prompt
    assert "do not add facts" in prompt.lower()
