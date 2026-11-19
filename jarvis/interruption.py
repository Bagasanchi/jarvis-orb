"""Local stop phrases and opt-in natural barge-in with buffered audio handoff."""
from collections import deque
import json
import threading
import time

from jarvis.config import SAMPLE_RATE
from jarvis.audio import input_stream
from jarvis import settings
from jarvis.echo import EchoCanceller

STOP_PHRASES = frozenset(('jarvis stop', 'stop jarvis', 'stop talking', 'stop'))


def is_stop_phrase(text):
    return ' '.join(text.lower().split()) in STOP_PHRASES


class VoiceInterruption:
    def __init__(self, speaker, model, enabled=None, listener=None, echo=False):
        self.speaker, self.model, self.listener = speaker, model, listener
        self.enabled = settings.get('voice_interrupt') if enabled is None else enabled
        self.natural = settings.get('natural_interrupt')
        self.done = threading.Event()
        self.thread = None
        self.echo = EchoCanceller(speaker.reference, settings.get("speech_threshold")) if echo else None

    def __enter__(self):
        if self.enabled:
            self.thread = threading.Thread(target=self._run, daemon=True, name='jarvis-stop-phrase')
            self.thread.start()
        return self

    def __exit__(self, *_):
        self.done.set()
        if self.thread:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise RuntimeError('Microphone monitor did not close; restart Jarvis')

    def _run(self):
        from vosk import KaldiRecognizer
        try:
            while not self.done.is_set():
                if self.speaker.playing.wait(.03):
                    break
            if self.done.is_set():
                return
            if self.natural:
                rec = KaldiRecognizer(self.model, SAMPLE_RATE)
            else:
                rec = KaldiRecognizer(self.model, SAMPLE_RATE, json.dumps(sorted(STOP_PHRASES) + ['[unk]']))
            # Keep the beginning of the correction so users need not repeat it.
            buffered = deque(maxlen=100)
            heard_since = None
            with input_stream() as stream:
                while not self.done.is_set():
                    if self.listener is not None and getattr(self.listener, "muted", None) is not None and self.listener.muted.is_set() is True:
                        break
                    raw, _ = stream.read(int(SAMPLE_RATE*.05))
                    if self.done.is_set():
                        break
                    raw = bytes(raw)
                    if not self.speaker.playing.is_set():
                        buffered.clear(); heard_since = None
                        rec.Reset()
                        continue
                    if self.echo is not None:
                        raw, near = self.echo.process(raw)
                        self.speaker.echo_status = self.echo.status
                        if not near:
                            buffered.clear(); heard_since = None
                            rec.Reset()
                            continue
                    buffered.append(raw)
                    complete = rec.AcceptWaveform(raw)
                    result = json.loads(rec.Result() if complete else rec.PartialResult())
                    text = result.get('text', result.get('partial', '')).strip()
                    stop = is_stop_phrase(text)
                    meaningful = self.natural and len(text.split()) >= 3
                    if meaningful and heard_since is None:
                        heard_since = time.monotonic()
                    if stop or (meaningful and time.monotonic()-heard_since >= .35):
                        if self.natural and not stop and self.listener:
                            self.listener.feed_prefix(list(buffered))
                        self.speaker.interrupt()
                        break
        except Exception as error:
            print('[Voice monitor unavailable]', type(error).__name__, '- keyboard interruption remains available.')
