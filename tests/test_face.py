import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from jarvis import face


class FaceTests(unittest.TestCase):
    def test_state_keeps_latest_and_preserves_transcripts(self):
        state = face.FaceState()
        state.update('listening', transcript='hello')
        state.update('thinking', reply='answer')
        window = object.__new__(face.FaceWindow)
        window.state = state
        window.transcript = window.reply = ''
        window.consume()
        self.assertEqual(window.mode, 'thinking')
        self.assertEqual(window.transcript, 'hello')
        self.assertEqual(window.reply, 'answer')

    def test_continuous_worker_and_shutdown(self):
        state = face.FaceState()
        assistant = Mock()
        assistant.wake.is_double_clap.return_value = True
        turns = iter(['hello', 'another question'])
        def listen():
            result = next(turns)
            if result == 'another question':
                state.stop.set()
            return result
        assistant.listener.listen.side_effect = listen
        assistant.handle_user_text.return_value = 'Hello, sir.'
        stream = Mock()
        stream.__enter__ = Mock(return_value=stream)
        stream.__exit__ = Mock(return_value=False)
        stream.read.return_value = (b'pcm', False)
        modules = {
            'jarvis.main': types.SimpleNamespace(JarvisAssistant=lambda: assistant),
            'jarvis.config': types.SimpleNamespace(SAMPLE_RATE=16000),
            'sounddevice': types.SimpleNamespace(InputStream=lambda **kwargs: stream),
        }
        with patch.dict(sys.modules, modules):
            face.assistant_worker(state)
        self.assertEqual(assistant.listener.listen.call_count, 2)
        assistant.handle_user_text.assert_called_once_with('hello')
        self.assertEqual(assistant.speaker.say.call_count, 2)
        assistant.shutdown.assert_called_once()
        modes = []
        while not state.events.empty():
            modes.append(state.events.get()[0])
        self.assertIn('idle', modes)
        self.assertEqual(modes.count('listening'), 2)

    def test_startup_error_is_visible(self):
        state = face.FaceState()
        def fail():
            raise RuntimeError('test startup failure')
        modules = {
            'jarvis.main': types.SimpleNamespace(JarvisAssistant=fail),
            'jarvis.config': types.SimpleNamespace(SAMPLE_RATE=16000),
            'jarvis.weather': types.SimpleNamespace(get_weather=lambda: ''),
            'sounddevice': types.SimpleNamespace(),
        }
        with patch.dict(sys.modules, modules), patch.object(face.traceback, 'print_exc'):
            face.assistant_worker(state)
        events = []
        while not state.events.empty():
            events.append(state.events.get())
        self.assertEqual(events[-1][0], 'error')
        self.assertIn('test startup failure', events[-1][1])


if __name__ == '__main__':
    unittest.main()
