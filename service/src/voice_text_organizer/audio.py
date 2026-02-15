from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from threading import Lock


class _RecordingSession:
    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._frames: list[bytes] = []
        self._stream = None

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "sounddevice is required for microphone recording. "
                "Install with: pip install sounddevice"
            ) from exc

        def callback(indata, _frames, _time, status) -> None:
            if status:
                return
            self._frames.append(indata.copy().tobytes())

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=callback,
        )
        self._stream.start()

    def stop_to_wav(self, path: Path) -> Path:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        if not self._frames:
            raise RuntimeError("no audio captured")

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(b"".join(self._frames))
        return path


class AudioRecorder:
    def __init__(self, temp_dir: str | None = None) -> None:
        self._lock = Lock()
        self._sessions: dict[str, _RecordingSession] = {}
        self._temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def start(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                raise RuntimeError("session already recording")
            rec = _RecordingSession()
            self._sessions[session_id] = rec
        rec.start()

    def stop(self, session_id: str) -> Path:
        with self._lock:
            rec = self._sessions.pop(session_id)
        output = self._temp_dir / f"{session_id}.wav"
        return rec.stop_to_wav(output)
