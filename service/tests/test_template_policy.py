from voice_text_organizer.policy import match_explicit_template_command


def test_meeting_template_requires_action_and_template_tokens() -> None:
    assert match_explicit_template_command("\u8bf7\u6309\u4f1a\u8bae\u7eaa\u8981\u6574\u7406") == "meeting_minutes"
    assert match_explicit_template_command("\u4f1a\u8bae\u5185\u5bb9\u5f88\u591a") is None


def test_task_template_allows_fuzzy_variants_but_not_ambiguous() -> None:
    assert match_explicit_template_command("\u5e2e\u6211\u5217\u4e2a\u4efb\u52a1\u6e05\u5355") == "task_list"
    assert match_explicit_template_command("\u5217\u4e00\u4e0b") is None


def test_translation_template_command_case_insensitive() -> None:
    assert match_explicit_template_command("Please TRANSLATE TO CHINESE") == "translation"
