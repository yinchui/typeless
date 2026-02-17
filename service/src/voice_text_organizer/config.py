from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Settings(BaseModel):
    default_mode: Literal["cloud", "local"] = "cloud"
    update_channel: Literal["stable", "beta"] = "stable"
    auto_template_confidence_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    fallback_to_local_on_cloud_error: bool = True
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1/chat/completions"
    siliconflow_model: str = "deepseek-ai/DeepSeek-V3"
    siliconflow_asr_url: str = "https://api.siliconflow.cn/v1/audio/transcriptions"
    siliconflow_asr_model: str = "FunAudioLLM/SenseVoiceSmall"
    siliconflow_api_key: str | None = Field(
        default_factory=lambda: os.getenv("SILICONFLOW_API_KEY")
    )
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"

    @model_validator(mode="after")
    def validate_cloud_key(self) -> "Settings":
        if self.default_mode == "cloud" and not self.siliconflow_api_key:
            raise ValueError("SILICONFLOW_API_KEY is required in cloud mode")
        return self
