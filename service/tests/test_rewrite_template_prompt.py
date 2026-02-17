from voice_text_organizer.rewrite import build_template_prompt


def test_light_edit_prompt_does_not_force_fixed_sections() -> None:
    messages = build_template_prompt("口头描述", template="light_edit")
    assert "Do not force rigid section templates" in messages[0]["content"]


def test_meeting_prompt_contains_minutes_sections() -> None:
    messages = build_template_prompt("今天讨论发布计划", template="meeting_minutes")
    assert "Topic" in messages[1]["content"]
    assert "Action Items" in messages[1]["content"]
