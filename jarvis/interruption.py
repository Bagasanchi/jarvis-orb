"""Listen locally for a stop phrase only while Jarvis audio is playing."""
import json
import os
import threading

from jarvis.config import SAMPLE_RATE

STOP_PHRASES = frozenset(("jarvis stop", "stop jarvis", "stop talking", "stop"))


def is_stop_phrase(text):
    return " ".join(text.lower().split()) in STOP_PHRASES


class VoiceInterruption:
    def __init__(self, speaker, model, enabled=None):
        self.speaker = speaker
        self.model = model
        self.enabled = os.getenv("JARVIS_VOICE_INTERRUPT", "1") != "0" if enabled is None else enabled
        self.done = threading.Event()
        self.thread = None

    def __enter__(self):
        if self.enabled:
            self.thread = threading.Thread(target=self._run, daemon=True, name="jarvis-stop-phrase")
            self.thread.start()
        return self

    def __exit__(self, *_):
        self.done.set()
        if self.thread:
            # The input stream is owned by this thread and released before
            # the conversation listener opens its own input stream.
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise RuntimeError("Stop-phrase microphone did not close; restart Jarvis")

    def _run(self):
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer
            while not self.done.is_set():
                if self.speaker.playing.wait(timeout=0.03):
                    break
            if self.done.is_set():
                return
            rec = KaldiRecognizer(self.model, SAMPLE_RATE, json.dumps(sorted(STOP_PHRASES) + ["[unk]"]))
            block = int(SAMPLE_RATE * 0.05)
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=block) as stream:
                while not self.done.is_set() and self.speaker.playing.is_set():
                    raw, overflow = stream.read(block)
                    if self.done.is_set() or not self.speaker.playing.is_set():
                        break
                    complete = rec.AcceptWaveform(raw.tobytes())
                    result = json.loads(rec.Result() if complete else rec.PartialResult())
                    if is_stop_phrase(result.get("text", result.get("partial", ""))):
                        self.speaker.interrupt()
                        print("[JARVIS] Voice interruption detected. Listening again.")
                        break
        except Exception as error:
            print(f"[Voice interruption unavailable: {type(error).__name__}] Space/Enter still stops speech.")
