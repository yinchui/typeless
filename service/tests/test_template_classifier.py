from voice_text_organizer.policy import decide_template_from_classifier


def test_low_confidence_falls_back_to_light_edit() -> None:
    decision = decide_template_from_classifier(
        predicted_template="meeting_minutes",
        confidence=0.61,
        threshold=0.72,
    )
    assert decision.template == "light_edit"
    assert decision.decision_type == "low_confidence_fallback_light"


def test_high_confidence_uses_predicted_template() -> None:
    decision = decide_template_from_classifier(
        predicted_template="task_list",
        confidence=0.88,
        threshold=0.72,
    )
    assert decision.template == "task_list"
    assert decision.decision_type == "auto_template"
