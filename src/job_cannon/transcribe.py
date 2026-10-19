"""Local speech-to-text for recorded answers, using faster-whisper.

faster-whisper is optional (``uv sync --extra voice``). Without it, recordings
are still kept, just not transcribed. The model is downloaded once on first
use; pick another with ``JOB_CANNON_WHISPER_MODEL`` (e.g. ``small.en``, or
``base`` for languages other than English).

``transcribe`` is blocking and CPU-heavy: call it through ``asyncio.to_thread``
and keep it away from the database connection.
"""

import importlib.util
import os
import threading
from pathlib import Path

MODEL_ENV_VAR = "JOB_CANNON_WHISPER_MODEL"
DEFAULT_MODEL = "base.en"

_lock = threading.Lock()
_model = None


def available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def transcribe(path: Path) -> str:
    """Transcribe one audio file. Runs one at a time; the model loads on first call."""
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(os.environ.get(MODEL_ENV_VAR) or DEFAULT_MODEL, device="cpu", compute_type="int8")
        segments, _info = _model.transcribe(str(path), vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
