"""Keep speaker playback out of recognition unless headphones are selected."""
from contextlib import contextmanager

from jarvis import settings


@contextmanager
def speech_session(speaker, model, listener=None):
    headphones = settings.get('audio_output') == 'headphones'
    echo = not headphones and settings.get('echo_cancellation')
    if headphones or echo:
        from jarvis.interruption import VoiceInterruption
        try:
            options = {'listener': listener}
            if echo:
                options['echo'] = True
            with VoiceInterruption(speaker, model, **options):
                yield
        finally:
            if not headphones:
                speaker.wait_for_quiet()
    else:
        # No microphone is opened during playback, even if legacy settings
        # still have natural_interrupt or voice_interrupt enabled.
        try:
            yield
        finally:
            speaker.wait_for_quiet()
