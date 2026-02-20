from __future__ import annotations

import io
import math
import re
import time
import wave
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import numpy as np


def _read_wav_mono_float(audio_path: str | Path) -> tuple[np.ndarray, int]:
    path = Path(audio_path)
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        frames = wf.getnframes()
        raw = wf.readframes(frames)

    if sampwidth != 2:
        raise ValueError("only 16-bit PCM wav is supported")

    pcm = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1).astype(np.int16)

    signal = pcm.astype(np.float32) / 32768.0
    if signal.size == 0:
        raise ValueError("empty audio")
    return signal, sample_rate


def _hz_to_mel(freq_hz: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(freq_hz) / 700.0)


def _mel_to_hz(mel: np.ndarray | float) -> np.ndarray | float:
    return 700.0 * (10.0 ** (np.asarray(mel) / 2595.0) - 1.0)


def _build_mel_filterbank(sample_rate: int, n_fft: int, n_filters: int = 26) -> np.ndarray:
    low_mel = _hz_to_mel(0.0)
    high_mel = _hz_to_mel(sample_rate / 2.0)
    mel_points = np.linspace(low_mel, high_mel, n_filters + 2)
    hz_points = _mel_to_hz(mel_points)
    bins = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)

    fbank = np.zeros((n_filters, n_fft // 2 + 1), dtype=np.float32)
    for idx in range(1, n_filters + 1):
        left = bins[idx - 1]
        center = bins[idx]
        right = bins[idx + 1]
        if center <= left:
            center = left + 1
        if right <= center:
            right = center + 1

        for j in range(left, center):
            fbank[idx - 1, j] = (j - left) / float(center - left)
        for j in range(center, right):
            fbank[idx - 1, j] = (right - j) / float(right - center)

    return fbank


def _frame_signal(signal: np.ndarray, frame_len: int, frame_step: int) -> np.ndarray:
    if signal.size <= frame_len:
        pad_len = frame_len - signal.size
        padded = np.pad(signal, (0, pad_len), mode="constant")
        return padded.reshape(1, frame_len)

    n_frames = 1 + int(math.ceil((signal.size - frame_len) / float(frame_step)))
    total_len = (n_frames - 1) * frame_step + frame_len
    padded = np.pad(signal, (0, max(0, total_len - signal.size)), mode="constant")

    indices = (
        np.tile(np.arange(0, frame_len), (n_frames, 1))
        + np.tile(np.arange(0, n_frames * frame_step, frame_step), (frame_len, 1)).T
    )
    return padded[indices]


def _dct_type_2(x: np.ndarray, num_ceps: int) -> np.ndarray:
    n = x.shape[1]
    k = np.arange(num_ceps, dtype=np.float32).reshape(-1, 1)
    n_idx = np.arange(n, dtype=np.float32).reshape(1, -1)
    basis = np.cos((math.pi / n) * (n_idx + 0.5) * k)
    return np.dot(x, basis.T)


def _compute_mfcc(signal: np.ndarray, sample_rate: int, num_ceps: int = 13) -> np.ndarray:
    emphasized = np.append(signal[0], signal[1:] - 0.97 * signal[:-1])

    frame_len = int(round(0.025 * sample_rate))
    frame_step = int(round(0.01 * sample_rate))
    n_fft = 512

    frames = _frame_signal(emphasized, frame_len, frame_step)
    frames *= np.hamming(frame_len)

    mag = np.absolute(np.fft.rfft(frames, n_fft))
    pow_spec = (1.0 / n_fft) * (mag ** 2)

    fbank = _build_mel_filterbank(sample_rate, n_fft, n_filters=26)
    mel_energy = np.dot(pow_spec, fbank.T)
    mel_energy = np.maximum(mel_energy, 1e-10)
    log_mel = np.log(mel_energy)

    mfcc = _dct_type_2(log_mel, num_ceps=num_ceps).astype(np.float32)
    mean = np.mean(mfcc, axis=0, keepdims=True)
    std = np.std(mfcc, axis=0, keepdims=True)
    std = np.where(std < 1e-6, 1.0, std)
    normalized = (mfcc - mean) / std

    if normalized.shape[0] > 220:
        indices = np.linspace(0, normalized.shape[0] - 1, 220).astype(int)
        normalized = normalized[indices]

    return normalized


def build_mfcc_fingerprint_bytes(audio_path: str | Path) -> bytes:
    signal, sample_rate = _read_wav_mono_float(audio_path)
    matrix = _compute_mfcc(signal, sample_rate)
    buffer = io.BytesIO()
    np.save(buffer, matrix.astype(np.float32), allow_pickle=False)
    return buffer.getvalue()


def decode_mfcc_fingerprint_bytes(blob: bytes) -> np.ndarray:
    buffer = io.BytesIO(blob)
    return np.load(buffer, allow_pickle=False).astype(np.float32)


def dtw_distance(a: np.ndarray, b: np.ndarray, window: int | None = None) -> float:
    if a.ndim != 2 or b.ndim != 2:
        raise ValueError("dtw inputs must be 2D arrays")
    if a.shape[1] != b.shape[1]:
        raise ValueError("dtw feature dimensions mismatch")

    n = a.shape[0]
    m = b.shape[0]
    if n == 0 or m == 0:
        return float("inf")

    if window is None:
        window = max(abs(n - m), 25)

    dp = np.full((n + 1, m + 1), np.inf, dtype=np.float64)
    dp[0, 0] = 0.0

    for i in range(1, n + 1):
        j_start = max(1, i - window)
        j_end = min(m + 1, i + window)
        for j in range(j_start, j_end):
            cost = float(np.linalg.norm(a[i - 1] - b[j - 1]))
            dp[i, j] = cost + min(dp[i - 1, j], dp[i, j - 1], dp[i - 1, j - 1])

    return float(dp[n, m] / (n + m))


def _collect_text_spans(voice_text: str) -> list[str]:
    spans: list[str] = []
    normalized = voice_text.strip()
    if not normalized:
        return spans

    spans.append(normalized)

    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", normalized)
    max_n = min(4, len(words))
    for n in range(1, max_n + 1):
        for idx in range(0, len(words) - n + 1):
            spans.append(" ".join(words[idx : idx + n]))

    for segment in re.findall(r"[\u4E00-\u9FFF]{2,20}", normalized):
        if len(segment) <= 8:
            spans.append(segment)
        for n in range(2, min(8, len(segment)) + 1):
            for idx in range(0, len(segment) - n + 1):
                spans.append(segment[idx : idx + n])

    deduped: list[str] = []
    seen: set[str] = set()
    for span in spans:
        lowered = span.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(span)
    return deduped


def _best_lexical_match(term: str, spans: list[str]) -> tuple[str, float]:
    term_lower = term.lower()
    best_match = ""
    best_score = 0.0

    for span in spans:
        span_lower = span.lower()
        if term_lower == span_lower:
            return span, 1.0
        score = SequenceMatcher(None, term_lower, span_lower).ratio()
        if score > best_score:
            best_score = score
            best_match = span

    return best_match, best_score


def select_candidate_terms(
    voice_text: str,
    active_terms: list[str],
    *,
    max_candidates: int = 20,
) -> list[dict[str, Any]]:
    if not active_terms or max_candidates <= 0:
        return []

    spans = _collect_text_spans(voice_text)
    scored: list[dict[str, Any]] = []
    for term in active_terms:
        best_match, score = _best_lexical_match(term, spans)
        scored.append(
            {
                "term": term,
                "best_match": best_match,
                "text_score": float(score),
            }
        )

    scored.sort(key=lambda item: (item["text_score"], item["term"].lower()), reverse=True)

    stage_a = [item for item in scored if item["text_score"] >= 0.55][:12]
    picked = {item["term"] for item in stage_a}

    stage_b = []
    for item in scored:
        if item["term"] in picked:
            continue
        stage_b.append(item)
        if len(stage_a) + len(stage_b) >= max_candidates:
            break

    return (stage_a + stage_b)[:max_candidates]


def enhance_voice_text(
    *,
    voice_text: str,
    audio_path: str | Path,
    active_terms: list[str],
    sample_lookup: dict[str, list[bytes]],
    timeout_ms: int = 900,
) -> str:
    if not voice_text.strip() or not active_terms:
        return voice_text
    if timeout_ms <= 0:
        return voice_text

    started = time.perf_counter()

    candidates = select_candidate_terms(voice_text, active_terms, max_candidates=20)
    if not candidates:
        return voice_text

    query_blob = build_mfcc_fingerprint_bytes(audio_path)
    query_matrix = decode_mfcc_fingerprint_bytes(query_blob)

    replacements: list[tuple[float, str, str]] = []
    for candidate in candidates:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if elapsed_ms > timeout_ms:
            return voice_text

        term = str(candidate["term"])
        term_lower = term.lower()
        if term_lower in voice_text.lower():
            continue

        samples = sample_lookup.get(term, [])
        if not samples:
            continue

        best_distance = float("inf")
        for sample_blob in samples:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if elapsed_ms > timeout_ms:
                return voice_text

            sample_matrix = decode_mfcc_fingerprint_bytes(sample_blob)
            distance = dtw_distance(query_matrix, sample_matrix, window=30)
            if distance < best_distance:
                best_distance = distance

        if not math.isfinite(best_distance):
            continue

        acoustic_conf = float(math.exp(-best_distance / 8.0))
        text_score = float(candidate["text_score"])
        best_match = str(candidate["best_match"])
        if not best_match:
            continue

        if acoustic_conf >= 0.86 and text_score >= 0.68 and best_match.lower() != term_lower:
            replacements.append((acoustic_conf * text_score, term, best_match))

    if not replacements:
        return voice_text

    result = voice_text
    replacements.sort(key=lambda item: item[0], reverse=True)
    for _, term, best_match in replacements:
        pattern = re.compile(re.escape(best_match), re.IGNORECASE)
        if pattern.search(result):
            result = pattern.sub(term, result, count=1)

    return result
