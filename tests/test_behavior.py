import json
import os
import unittest
from unittest.mock import Mock, patch
import numpy as np

from jarvis import app_opener, main, stt, weather


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.assistant = object.__new__(main.JarvisAssistant)
        self.assistant.brain = Mock()

    def test_code_question_does_not_open_app(self):
        with patch.object(main, 'open_app') as launch:
            self.assistant.handle_user_text('Explain this code')
            launch.assert_not_called()
        self.assistant.brain.think.assert_called_once()

    def test_explicit_app_request(self):
        with patch.object(main, 'open_app', return_value=(True, 'opened')) as launch:
            self.assertEqual(self.assistant.handle_user_text('Open notepad'), 'opened')
            launch.assert_called_once_with('notepad')

    def test_multiword_weather_location(self):
        with patch.object(main, 'get_weather', return_value='weather') as lookup:
            self.assistant.handle_user_text("What is the weather in New York?")
            lookup.assert_called_once_with('New York')

    def test_plain_greeting_does_not_fetch_weather(self):
        self.assistant._greeting_shown = False
        self.assistant.speaker = Mock()
        self.assistant.listener = Mock()
        self.assistant.listener.listen.return_value = ''
        with patch.object(main, 'get_weather') as lookup:
            self.assistant._on_woken()
            lookup.assert_not_called()
        self.assertIn('Hello, sir.', self.assistant.speaker.say.call_args_list[0].args[0])

    def test_unknown_app_is_not_passed_to_shell(self):
        with patch.object(app_opener.subprocess, 'run') as run:
            ok, _ = app_opener.open_app('notepad & calc')
            self.assertFalse(ok)
            run.assert_not_called()

    def test_failed_weather_does_not_invent_conditions(self):
        with patch.object(weather.requests, 'get', side_effect=OSError):
            self.assertIn("couldn't retrieve", weather.get_weather('Tokyo'))


class RecognitionTests(unittest.TestCase):
    def listener(self):
        listener = object.__new__(stt.Listener)
        listener.rec = Mock()
        listener.rec.AcceptWaveform.return_value = False
        listener.rec.FinalResult.return_value = json.dumps({'text':'hello'})
        return listener

    def test_silence_timer_does_not_reset_each_block(self):
        listener = self.listener()
        stream = Mock()
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        count = [0]
        def read(_):
            count[0] += 1
            return (np.full((800,1), 2000 if count[0]==1 else 0, dtype=np.int16), False)
        stream.read.side_effect = read
        ticks = iter(i*.5 for i in range(100))
        with patch('sounddevice.InputStream', return_value=stream), patch.object(stt.time, 'monotonic', side_effect=lambda:next(ticks)):
            self.assertEqual(listener.listen(), 'hello')
        self.assertLess(count[0], 8)
        listener.rec.Reset.assert_called_once()

    def test_endpoint_result_is_not_lost(self):
        listener = self.listener()
        listener.rec.AcceptWaveform.return_value = True
        listener.rec.Result.return_value = json.dumps({'text':'open notepad'})
        listener.rec.FinalResult.return_value = json.dumps({'text':''})
        stream = Mock()
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        stream.read.return_value = (np.zeros((800,1),dtype=np.int16),False)
        with patch('sounddevice.InputStream',return_value=stream):
            self.assertEqual(listener.listen(), 'open notepad')


if __name__ == '__main__':
    unittest.main()
