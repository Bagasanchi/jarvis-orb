"""Keep speaker playback out of recognition unless headphones are selected."""
from contextlib import contextmanager

from jarvis import settings


@contextmanager
def speech_session(speaker, model, listener=None):
    if settings.get('audio_output') == 'headphones':
        from jarvis.interruption import VoiceInterruption
        with VoiceInterruption(speaker, model, listener=listener):
            yield
    else:
        # No microphone is opened during playback, even if legacy settings
        # still have natural_interrupt or voice_interrupt enabled.
        try:
            yield
        finally:
            speaker.wait_for_quiet()
