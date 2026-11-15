"""Local Vosk wake phrase detection. No clap detection or clap microphone loop."""
import json
from jarvis.audio import input_stream
from jarvis.config import SAMPLE_RATE
from jarvis import settings


def wait_for_wake(model, wake_event, stop_event):
    if wake_event.is_set():
        return not stop_event.is_set()
    if not settings.get('wake_enabled'):
        while not stop_event.is_set():
            if wake_event.wait(.1):
                return True
        return False
    from vosk import KaldiRecognizer
    phrase = ' '.join(settings.get('wake_phrase').lower().split())
    rec = KaldiRecognizer(model, SAMPLE_RATE, json.dumps([phrase, '[unk]']))
    with input_stream() as stream:
        while not stop_event.is_set() and not wake_event.is_set():
            raw, _ = stream.read(int(SAMPLE_RATE * .05))
            complete = rec.AcceptWaveform(bytes(raw))
            result = json.loads(rec.Result() if complete else rec.PartialResult())
            if result.get('text', result.get('partial', '')).strip() == phrase:
                return True
    return not stop_event.is_set()
