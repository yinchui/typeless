from voice_text_organizer.policy import decide_processing_mode


def test_no_selected_text_always_transcribe_only() -> None:
    mode = decide_processing_mode(
        "请问今天上海天气怎么样",
        selected_text=None,
        existing_text="some existing editor content",
    )
    assert mode == "transcribe_only"


def test_selected_text_translation_command_hits_whitelist() -> None:
    mode = decide_processing_mode(
        "请帮我翻译成中文",
        selected_text="This is a test.",
        existing_text=None,
    )
    assert mode == "selected_whitelist_rewrite"


def test_selected_text_non_whitelist_command_is_transcribe_only() -> None:
    mode = decide_processing_mode(
        "帮我总结一下",
        selected_text="This is a test.",
        existing_text=None,
    )
    assert mode == "transcribe_only"


def test_selected_text_translation_command_english_case_insensitive() -> None:
    mode = decide_processing_mode(
        "Please TRANSLATE TO CHINESE",
        selected_text="This is a test.",
        existing_text=None,
    )
    assert mode == "selected_whitelist_rewrite"
