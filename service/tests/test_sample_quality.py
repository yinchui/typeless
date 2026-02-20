from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from voice_text_organizer.main import _evaluate_sample_audio_quality


def _write_pcm16_wav(path: Path, pcm: np.ndarray, sample_rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(np.asarray(pcm, dtype=np.int16).tobytes())


def test_sample_quality_accepts_quiet_but_audible_voice(tmp_path: Path) -> None:
    sample_rate = 16000
    seconds = 1.2
    frames = int(sample_rate * seconds)
    time_axis = np.arange(frames, dtype=np.float32) / float(sample_rate)

    # Quiet but still audible tone-like speech proxy (~0.01 peak, ~0.007 rms).
    pcm = (np.sin(2.0 * np.pi * 220.0 * time_axis) * 320.0).astype(np.int16)
    # Add brief leading/trailing silence to mimic real utterances.
    pcm[: int(sample_rate * 0.08)] = 0
    pcm[-int(sample_rate * 0.08) :] = 0

    audio_path = tmp_path / "quiet-audible.wav"
    _write_pcm16_wav(audio_path, pcm, sample_rate=sample_rate)

    quality = _evaluate_sample_audio_quality(audio_path)
    assert quality["duration_ms"] >= 1100
    assert quality["quality_score"] > 0.0


def test_sample_quality_rejects_near_silence(tmp_path: Path) -> None:
    sample_rate = 16000
    seconds = 1.0
    frames = int(sample_rate * seconds)
    time_axis = np.arange(frames, dtype=np.float32) / float(sample_rate)

    # Near-silent signal should still be rejected.
    pcm = (np.sin(2.0 * np.pi * 220.0 * time_axis) * 25.0).astype(np.int16)

    audio_path = tmp_path / "near-silence.wav"
    _write_pcm16_wav(audio_path, pcm, sample_rate=sample_rate)

    with pytest.raises(ValueError, match="sample volume too low"):
        _evaluate_sample_audio_quality(audio_path)
