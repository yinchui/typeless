from voice_text_organizer.asr import normalize_asr_text


def test_normalize_asr_text_strips_whitespace() -> None:
    assert normalize_asr_text("  hello    world  ") == "hello world"
