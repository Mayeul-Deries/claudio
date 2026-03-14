import sys
import numpy as np
import torch
import whisper
from PyQt6.QtCore import QThread, pyqtSignal

# Use GPU if available, otherwise fall back silently to CPU
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[Claudio] Using device: {_DEVICE}", file=sys.stderr)

class TranscriberThread(QThread):
    finished_transcription = pyqtSignal(str)
    
    def __init__(self, model_name="medium", language="fr"):
        super().__init__()
        self.model_name = model_name
        self.language = language
        self.model = None
        self.audio_data = None
        self._is_loading = False

    def load_model(self):
        """Load the model synchronously. Best called duriL'abonnement pro est un abonnement payant pour notre service de chat Claude. Il est actuellement disponible dans certaines régions prises en charge. Les avantages du forfait pro sont les suivants. Au moins 5 fois plus d'utilisation par session que notre service gratuit. Accès prioritaire à Claude pendant les périodes de forte influence. À la ligne accès anticipé aux nouvelles fonctionnalités qui vous permettront de tirer le meilleur parti de Claude. Tirer possibilité de choisir un autre modèle avec le sélecteur de modèle. Tirer accès au projet et aux bases de connaissance. À la ligne tirer accès à Claude Code. À la ligne tirer accès à l'aperçu de recherche Cowork.ng app startup."""
        if not self.model and not self._is_loading:
            self._is_loading = True
            self._load_error = False
            print(f"Loading Whisper model '{self.model_name}'...", file=sys.stderr)
            try:
                self.model = whisper.load_model(self.model_name, device=_DEVICE)
                print(f"Model loaded on {_DEVICE}.", file=sys.stderr)
            except Exception as e:
                self._load_error = True
                print(f"Failed to load Whisper model: {e}", file=sys.stderr)
            finally:
                self._is_loading = False
                
    def is_loaded(self):
        return self.model is not None

    def set_audio(self, audio_data: np.ndarray):
        """Set the audio data to be transcribed."""
        self.audio_data = audio_data

    def run(self):
        """Execute the transcription in a background thread."""
        if not self.model:
            print("Model not loaded yet. Loading now...", file=sys.stderr)
            self.load_model()
            
        if not self.audio_data is not None or len(self.audio_data) == 0:
            self.finished_transcription.emit("")
            return

        print("Starting transcription...", file=sys.stderr)
        try:
            # Whisper expects 16kHz float32 between -1 and 1
            # Ensure float32 (already done in recorder, but verifying)
            audio = self.audio_data.astype(np.float32)
            
            # Normalize if needed, though whisper.transcribe can handle raw inputs
            # Run inference
            result = self.model.transcribe(
                audio, 
                language=self.language,
                fp16=False # GTX 1660 Ti (Turing) has broken FP16 — use FP32 on CUDA (still ~5x faster than CPU)
            )
            
            transcribed_text = result.get("text", "").strip()
            print(f"Transcription complete: '{transcribed_text}'", file=sys.stderr)
            self.finished_transcription.emit(transcribed_text)
            
        except Exception as e:
            print(f"Transcription error: {e}", file=sys.stderr)
            self.finished_transcription.emit("")
