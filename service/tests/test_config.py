import pytest

from voice_text_organizer.config import Settings


def test_cloud_mode_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    with pytest.raises(ValueError):
        Settings(default_mode="cloud")


def test_default_model_is_deepseek_v3() -> None:
    settings = Settings(default_mode="cloud", siliconflow_api_key="test-key")
    assert settings.siliconflow_model == "deepseek-ai/DeepSeek-V3"
