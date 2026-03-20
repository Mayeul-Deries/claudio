"""Whisper transcription module.

Keeps the model loaded in memory between calls.
Each transcription runs in a fresh QThread to avoid the
QThread.start()-after-finished no-op bug.
"""
import sys
import numpy as np
import torch
from faster_whisper import WhisperModel
from PyQt6.QtCore import QThread, pyqtSignal

# Use GPU if available, otherwise fall back silently to CPU
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_COMPUTE_TYPE = "float32" if _DEVICE == "cuda" else "int8"
print(f"[Claudio] Using device: {_DEVICE} with compute_type: {_COMPUTE_TYPE}", file=sys.stderr)


class _InferenceThread(QThread):
    """Single-use thread that runs one whisper transcription then terminates."""
    finished_transcription = pyqtSignal(str)

    def __init__(self, model, audio_data: np.ndarray, language: str):
        super().__init__()
        self._model = model
        self._audio_data = audio_data
        self._language = language

    def run(self):
        print("Starting transcription...", file=sys.stderr)
        try:
            audio = self._audio_data.astype(np.float32)

            # === DEBUG ===
            duration = len(audio) / 16000
            rms = float(np.sqrt(np.mean(np.square(audio))))
            print(f"[DEBUG] audio: {len(audio)} samples, {duration:.1f}s, RMS={rms:.5f}", file=sys.stderr)
            # =============

            segments, info = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=5
            )

            # Consume the generator
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)
                
            text = " ".join(text_parts).strip()

            # === DEBUG ===
            print(f"[DEBUG] info: language={info.language}, prob={info.language_probability:.3f}", file=sys.stderr)
            # =============
            print(f"Transcription complete: '{text}'", file=sys.stderr)
            self.finished_transcription.emit(text)
        except Exception as e:
            print(f"Transcription error: {e}", file=sys.stderr)
            self.finished_transcription.emit("")


class TranscriberThread:
    """Owns the Whisper model and spawns a fresh _InferenceThread per call."""

    finished_transcription: pyqtSignal  # exposed so main.py can connect

    def __init__(self, model_name: str = "medium", language: str = "fr"):
        self.model_name = model_name
        self.language = language
        self.model = None
        self._is_loading = False
        self._load_error = False
        # Keep a ref to the current thread so it isn't garbage-collected mid-run
        self._active_thread: _InferenceThread | None = None
        # Expose a dummy pyqtSignal target so main.py connect() works
        # The real signal comes from _InferenceThread; we proxy it via a callback
        self._on_done_callback = None

    # ------------------------------------------------------------------ #
    # Model loading                                                        #
    # ------------------------------------------------------------------ #

    def load_model(self):
        """Load the Whisper model synchronously. Call from a background thread."""
        if self.model is not None or self._is_loading:
            return
        self._is_loading = True
        self._load_error = False
        print(f"Loading Whisper model '{self.model_name}'...", file=sys.stderr)
        try:
            self.model = WhisperModel(self.model_name, device=_DEVICE, compute_type=_COMPUTE_TYPE)
            print(f"Model loaded on {_DEVICE}.", file=sys.stderr)
        except Exception as e:
            self._load_error = True
            print(f"Failed to load Whisper model: {e}", file=sys.stderr)
        finally:
            self._is_loading = False

    def is_loaded(self) -> bool:
        return self.model is not None

    # ------------------------------------------------------------------ #
    # Transcription                                                        #
    # ------------------------------------------------------------------ #

    def transcribe(self, audio_data: np.ndarray, callback):
        """Start transcription in a fresh background thread.

        Args:
            audio_data: 16 kHz float32 mono numpy array.
            callback: callable(str) invoked on the Qt thread when done.
        """
        if self.model is None:
            print("Model not loaded — cannot transcribe.", file=sys.stderr)
            callback("")
            return

        thread = _InferenceThread(self.model, audio_data, self.language)
        thread.finished_transcription.connect(callback)
        # Hold a reference so the GC doesn't collect the thread object
        self._active_thread = thread
        thread.start()
