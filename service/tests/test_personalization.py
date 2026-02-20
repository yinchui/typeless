from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from voice_text_organizer.personalization import (
    build_mfcc_fingerprint_bytes,
    decode_mfcc_fingerprint_bytes,
    dtw_distance,
    enhance_voice_text,
    select_candidate_terms,
)


def _write_sine(path: Path, *, frequency: float = 440.0, seconds: float = 0.8, sample_rate: int = 16000) -> None:
    total = int(seconds * sample_rate)
    t = np.arange(total, dtype=np.float32) / float(sample_rate)
    signal = 0.3 * np.sin(2.0 * math.pi * frequency * t)
    pcm = np.clip(signal * 32767.0, -32768, 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def test_mfcc_fingerprint_roundtrip(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    _write_sine(wav)

    blob = build_mfcc_fingerprint_bytes(wav)
    decoded = decode_mfcc_fingerprint_bytes(blob)

    assert isinstance(blob, bytes)
    assert decoded.ndim == 2
    assert decoded.shape[1] == 13


def test_dtw_distance_prefers_similar_sequence() -> None:
    a = np.array([[0.1, 0.2], [0.2, 0.3], [0.3, 0.4]], dtype=np.float32)
    b = np.array([[0.1, 0.2], [0.2, 0.31], [0.3, 0.41]], dtype=np.float32)
    c = np.array([[2.0, 1.9], [2.1, 1.8], [2.2, 1.7]], dtype=np.float32)

    near = dtw_distance(a, b)
    far = dtw_distance(a, c)

    assert near < far


def test_select_candidate_terms_prioritizes_text_similarity() -> None:
    candidates = select_candidate_terms(
        "please sync typeless release notes",
        ["Typeless", "Kubernetes", "Notebook"],
        max_candidates=2,
    )

    assert candidates[0]["term"] == "Typeless"
    assert len(candidates) == 2


def test_enhance_voice_text_replaces_match_when_confident(tmp_path: Path) -> None:
    wav = tmp_path / "term.wav"
    _write_sine(wav, frequency=520.0)
    fp = build_mfcc_fingerprint_bytes(wav)

    enhanced = enhance_voice_text(
        voice_text="type less release is ready",
        audio_path=wav,
        active_terms=["Typeless", "Kubernetes"],
        sample_lookup={"Typeless": [fp], "Kubernetes": []},
        timeout_ms=900,
    )

    assert "Typeless" in enhanced


def test_enhance_voice_text_returns_original_on_timeout(tmp_path: Path) -> None:
    wav = tmp_path / "term.wav"
    _write_sine(wav, frequency=520.0)
    fp = build_mfcc_fingerprint_bytes(wav)

    original = "type less release is ready"
    enhanced = enhance_voice_text(
        voice_text=original,
        audio_path=wav,
        active_terms=["Typeless"],
        sample_lookup={"Typeless": [fp]},
        timeout_ms=0,
    )

    assert enhanced == original
