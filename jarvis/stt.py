import json
import time
from vosk import Model, KaldiRecognizer
from jarvis.config import SAMPLE_RATE, VAD_SILENCE_DURATION, MAX_SPEECH_DURATION, MODEL_DIR


class Listener:
    BLOCK_MS = 50
    BLOCK_SIZE = int(BLOCK_MS * SAMPLE_RATE / 1000)

    def __init__(self):
        model_path = MODEL_DIR
        print(f"Loading Vosk model from {model_path}...")
        self.model = Model(model_path)
        self.rec = KaldiRecognizer(self.model, SAMPLE_RATE)

    def listen(self) -> str:
        """Record until silence, return transcript."""
        import sounddevice as sd
        import numpy as np

        def rms(chunk):
            return float(((chunk.astype(float) / 32768.0) ** 2).mean() ** 0.5)

        print("Listening for your command...")
        self.rec.Reset()
        segments = []
        t_start = time.monotonic()
        silent_after_speech = None
        has_speech = False

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=self.BLOCK_SIZE) as stream:
            while time.monotonic() - t_start < MAX_SPEECH_DURATION:
                try:
                    raw, overflow = stream.read(self.BLOCK_SIZE)
                except Exception as e:
                    print(f"[STT] Stream error: {e}")
                    break

                chunk = np.frombuffer(raw, dtype=np.int16)
                r = rms(chunk)
                if self.rec.AcceptWaveform(chunk.tobytes()):
                    segment = json.loads(self.rec.Result()).get("text", "").strip()
                    if segment:
                        segments.append(segment)
                        break

                if r > 0.008:
                    has_speech = True
                    silent_after_speech = None
                else:
                    if has_speech and silent_after_speech is None:
                        silent_after_speech = time.monotonic()
                    if has_speech and silent_after_speech is not None:
                        elapsed = time.monotonic() - silent_after_speech
                        if elapsed >= VAD_SILENCE_DURATION:
                            break

        result = json.loads(self.rec.FinalResult())
        final = (result.get("text") or "").strip()
        if final:
            segments.append(final)
        text = " ".join(segments)
        if text:
            print(f"USER said: '{text}'")
        return text
