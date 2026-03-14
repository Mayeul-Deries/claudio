import queue
import sys
import numpy as np
import sounddevice as sd

class AudioRecorder:
    def __init__(self, samplerate=16000, channels=1):
        self.samplerate = samplerate
        self.channels = channels
        self.q = queue.Queue()
        self.stream = None
        self.is_recording = False
        self.audio_data = []

    def _audio_callback(self, indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(status, file=sys.stderr)
        # Put audio block into queue
        self.q.put(indata.copy())
        
        # Keep track of all audio for the final recording
        if self.is_recording:
            self.audio_data.append(indata.copy())

    def start(self):
        self.audio_data = []
        self.q.queue.clear()
        
        try:
            self.stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                dtype='float32',
                callback=self._audio_callback
            )
            self.stream.start()
            self.is_recording = True
            return True
        except Exception as e:
            print(f"Error starting audio stream: {e}", file=sys.stderr)
            return False

    def stop(self) -> np.ndarray:
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            
        if not self.audio_data:
            return np.array([], dtype=np.float32)
            
        # Concatenate all recorded blocks
        return np.concatenate(self.audio_data, axis=0).flatten()

    def get_current_amplitude(self) -> float:
        """Calculate RMS amplitude of the most recent audio block for the UI."""
        if not self.is_recording or self.q.empty():
            return 0.0
            
        try:
            # Look at the most recent block in the queue without removing it
            latest_block = self.q.queue[-1]
            # Calculate RMS amplitude
            rms = np.sqrt(np.mean(np.square(latest_block)))
            return float(rms)
        except Exception:
            return 0.0
