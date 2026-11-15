"""Cancellable recognition with audio handoff from an interrupted response."""
from collections import deque
import json
import time

from vosk import Model, KaldiRecognizer
from jarvis.config import SAMPLE_RATE, MAX_SPEECH_DURATION, MODEL_DIR
from jarvis import settings
from jarvis.audio import input_stream, rms


class Listener:
    BLOCK_SIZE = int(SAMPLE_RATE * .05)

    def __init__(self):
        self.model = Model(MODEL_DIR)
        self.rec = KaldiRecognizer(self.model, SAMPLE_RATE)
        self.prefix = deque()

    def feed_prefix(self, chunks):
        self.prefix.extend(chunks)

    def listen(self, stop_event=None):
        self.rec.Reset()
        segments = []
        started = time.monotonic()
        silence = None
        has_speech = False
        threshold = settings.get('speech_threshold')
        duration = settings.get('silence_seconds')
        with input_stream() as stream:
            while time.monotonic()-started < MAX_SPEECH_DURATION:
                if stop_event is not None and stop_event.is_set():
                    return ''
                if self.prefix:
                    raw = self.prefix.popleft()
                else:
                    raw, _ = stream.read(self.BLOCK_SIZE)
                    raw = bytes(raw)
                if self.rec.AcceptWaveform(raw):
                    segment = json.loads(self.rec.Result()).get('text', '').strip()
                    if segment:
                        segments.append(segment)
                        break
                if rms(raw) >= threshold:
                    has_speech, silence = True, None
                elif has_speech:
                    if silence is None:
                        silence = time.monotonic()
                    if time.monotonic()-silence >= duration:
                        break
        final = json.loads(self.rec.FinalResult()).get('text', '').strip()
        if final:
            segments.append(final)
        # Any unused prefix belongs to this utterance, never the next one.
        self.prefix.clear()
        return ' '.join(segments)
