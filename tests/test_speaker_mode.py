from contextlib import nullcontext
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from jarvis import main, settings, tts
from jarvis.speech_session import speech_session


class SpeakerModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {'JARVIS_DATA_DIR': self.temp.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.settings = patch.object(settings, 'get', side_effect=lambda key: settings.load()[key])
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def test_old_natural_interruption_setting_cannot_open_mic_in_speaker_mode(self):
        # Old installations have no audio_output key and may enable both triggers.
        (Path(self.temp.name)/'settings.json').write_text('{"natural_interrupt":true,"voice_interrupt":true,"echo_cancellation":false}')
        speaker = Mock()
        with patch('jarvis.interruption.VoiceInterruption') as monitor, patch('sounddevice.InputStream') as mic:
            with speech_session(speaker, Mock()):
                pass
        monitor.assert_not_called()
        mic.assert_not_called()
        speaker.wait_for_quiet.assert_called_once()

    def test_greeting_and_streamed_reply_both_use_speaker_mode(self):
        settings.save({'audio_output': 'speakers', 'natural_interrupt': True, 'echo_cancellation': False})
        assistant = object.__new__(main.JarvisAssistant)
        assistant.listener = types.SimpleNamespace(model=Mock())
        assistant.brain = types.SimpleNamespace(history=[])
        assistant.reply_stream = lambda text, cancel: iter(['Jarvis stop. ', 'Stop talking.'])
        with patch.object(tts.pygame.mixer, 'get_init', return_value=True):
            assistant.speaker = tts.Speaker()
        with patch('jarvis.interruption.VoiceInterruption') as monitor, patch.object(assistant.speaker, '_speak_segment', return_value=True), patch.object(assistant.speaker, 'wait_for_quiet') as settle:
            self.assertTrue(assistant.speak('Hello sir.'))
            self.assertTrue(assistant.respond('Explain interruption commands'))
        monitor.assert_not_called()
        self.assertEqual(settle.call_count, 2)
        self.assertFalse(assistant.speaker.interrupted.is_set())

    def test_headphone_mode_retains_voice_interruption(self):
        settings.save({'audio_output': 'headphones'})
        speaker, listener, model = Mock(), Mock(), Mock()
        with patch('jarvis.interruption.VoiceInterruption', return_value=nullcontext()) as monitor:
            with speech_session(speaker, model, listener):
                pass
        monitor.assert_called_once_with(speaker, model, listener=listener)
        speaker.wait_for_quiet.assert_not_called()

    def test_echo_tail_is_respected_after_playback(self):
        with patch.object(tts.pygame.mixer, 'get_init', return_value=True):
            speaker = tts.Speaker()
        speaker.last_playback_ended = 10
        speaker.closed = Mock()
        with patch.object(tts.time, 'monotonic', return_value=10.1):
            speaker.wait_for_quiet()
        self.assertAlmostEqual(speaker.closed.wait.call_args.args[0], .3)

    def test_no_unnecessary_delay_after_generation_was_cancelled(self):
        with patch.object(tts.pygame.mixer, 'get_init', return_value=True):
            speaker = tts.Speaker()
        speaker.closed = Mock()
        speaker.wait_for_quiet()
        speaker.closed.wait.assert_not_called()

    def test_keyboard_can_still_cancel_speaker_mode_playback(self):
        settings.save({'audio_output': 'speakers'})
        with patch.object(tts.pygame.mixer, 'get_init', return_value=True):
            speaker = tts.Speaker()
        playing = threading.Event()
        def playback(text):
            playing.set()
            speaker.interrupted.wait(1)
            return False
        outcome = []
        with patch.object(speaker, '_speak_segment', side_effect=playback):
            def speak():
                with speech_session(speaker, Mock()):
                    outcome.append(speaker.say('This is an answer.'))
            worker = threading.Thread(target=speak)
            worker.start()
            self.assertTrue(playing.wait(1))
            self.assertTrue(speaker.interrupt())
            worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome, [False])


if __name__ == '__main__':
    unittest.main()
