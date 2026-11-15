import asyncio
import json
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np
from jarvis import tts
from jarvis.face import FaceState
from jarvis.interruption import VoiceInterruption, is_stop_phrase


class SpeechCancellationTests(unittest.TestCase):
    def setUp(self):
        self.music = Mock()
        self.mixer = patch.object(tts.pygame, 'mixer', types.SimpleNamespace(
            get_init=lambda: True, music=self.music))
        self.mixer.start()
        self.addCleanup(self.mixer.stop)
        self.speaker = tts.Speaker()

    def test_interrupt_during_generation_never_plays_late_audio(self):
        started = threading.Event()
        cancelled = threading.Event()
        async def generate(text):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        self.speaker._generate_audio = generate
        result = []
        worker = threading.Thread(target=lambda: result.append(self.speaker.say('test')))
        worker.start()
        self.assertTrue(started.wait(1))
        self.assertTrue(self.speaker.interrupt())
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
        self.assertTrue(cancelled.is_set())
        self.music.play.assert_not_called()
        self.assertFalse(self.speaker.active.is_set())

    def test_interrupt_playback_then_next_reply_still_works(self):
        async def generate(text): pass
        self.speaker._generate_audio = generate
        self.music.get_busy.side_effect = lambda: not self.speaker.interrupted.is_set()
        worker = threading.Thread(target=lambda: self.speaker.say('first'))
        worker.start()
        self.assertTrue(self.speaker.playing.wait(1))
        self.speaker.interrupt()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertFalse(self.speaker.playing.is_set())
        self.music.stop.assert_called()
        self.music.unload.assert_called()
        self.music.get_busy.side_effect = None
        self.music.get_busy.return_value = False
        self.assertTrue(self.speaker.say('second'))
        self.assertFalse(self.speaker.interrupted.is_set())

    def test_idle_interrupt_does_not_cancel_next_reply(self):
        self.assertFalse(self.speaker.interrupt())
        self.assertFalse(self.speaker.interrupted.is_set())

    def test_face_state_requests_interrupt(self):
        state = FaceState()
        state.speaker = self.speaker
        self.speaker.active.set()
        self.assertTrue(state.interrupt_speech())
        self.assertTrue(self.speaker.interrupted.is_set())


class VoiceMonitorTests(unittest.TestCase):
    def test_only_explicit_stop_phrases(self):
        for text in ('Jarvis stop','STOP TALKING',' stop ','stop jarvis'):
            self.assertTrue(is_stop_phrase(text))
        for text in ('hello', '[unk]', 'do not stop talking', '', 'the bus stop'):
            self.assertFalse(is_stop_phrase(text))

    def test_partial_stop_phrase_stops_speech_and_releases_mic(self):
        speaker = types.SimpleNamespace(playing=threading.Event(), interrupt=Mock())
        speaker.playing.set()
        rec = Mock()
        rec.AcceptWaveform.return_value = False
        rec.PartialResult.return_value = json.dumps({'partial':'jarvis stop'})
        stream = Mock()
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        stream.read.return_value = (np.zeros((800,1),dtype=np.int16),False)
        with patch('vosk.KaldiRecognizer',return_value=rec), patch('sounddevice.InputStream',return_value=stream):
            with VoiceInterruption(speaker,Mock()) as monitor:
                monitor.thread.join(1)
        speaker.interrupt.assert_called_once()
        stream.__exit__.assert_called_once()

    def test_disabled_monitor_does_not_open_mic(self):
        with patch('sounddevice.InputStream') as stream:
            with VoiceInterruption(Mock(),Mock(),enabled=False) as monitor:
                self.assertIsNone(monitor.thread)
            stream.assert_not_called()

    def test_cancelled_generation_does_not_open_mic(self):
        speaker = types.SimpleNamespace(playing=threading.Event())
        with patch('sounddevice.InputStream') as stream:
            with VoiceInterruption(speaker,Mock()): pass
            stream.assert_not_called()


if __name__ == '__main__':
    unittest.main()
