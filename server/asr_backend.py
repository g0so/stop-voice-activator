"""Optional local, open-source ASR integration."""

from __future__ import annotations

from pathlib import Path
from threading import Lock


class WhisperBackend:
    """Lazy faster-whisper wrapper so the TCP server can start before model load."""

    def __init__(self, model_name: str = "tiny.en", language: str | None = "en") -> None:
        self.model_name = model_name
        self.language = language
        self._model = None
        self._lock = Lock()

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "faster-whisper is not installed; install server/requirements.txt "
                    "or launch with --no-asr"
                ) from exc
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, wav_path: Path) -> dict:
        with self._lock:
            model = self._load()
            segments, info = model.transcribe(
                str(wav_path),
                language=self.language,
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            materialized = list(segments)
        return {
            "text": " ".join(segment.text.strip() for segment in materialized).strip(),
            "language": info.language,
            "language_probability": float(info.language_probability),
            "segments": [
                {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
                for s in materialized
            ],
        }
