import asyncio
from collections import deque
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from jarvis import audio, brain, main, screen, settings, stt, tts, wake
from jarvis.desktop import Desktop
from jarvis.memory import Memory


class IsolatedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'JARVIS_DATA_DIR': str(self.root)})
        self.env.start(); self.addCleanup(self.env.stop)


class MemoryAndActionsTests(IsolatedTests):
    def setUp(self):
        super().setUp()
        self.assistant = object.__new__(main.JarvisAssistant)
        self.assistant.memory = Memory()
        self.assistant.brain = brain.Brain(memory=self.assistant.memory)
        self.assistant.desktop = Desktop()
        self.assistant.confirm = Mock(return_value=True)
        self.addCleanup(self.assistant.desktop.close)

    def test_explicit_memory_survives_restart_and_can_be_deleted(self):
        result = self.assistant.handle_user_text('remember that I study Japanese')
        self.assertIn('Remembered', result)
        fresh = Memory()
        self.assertIn('Japanese', fresh.context())
        self.assertIn('Japanese', self.assistant.brain._messages('What do I study?')[0]['content'])
        self.assistant.handle_user_text('forget one')
        self.assertEqual(fresh.list(), [])

    def test_notes_are_separate_from_ai_memory(self):
        self.assistant.handle_user_text('take a note buy milk')
        self.assertIn('buy milk', self.assistant.handle_user_text('read my notes'))
        self.assertEqual(self.assistant.memory.context(), '')

    def test_forget_everything_clears_notes_and_conversation(self):
        self.assistant.handle_user_text('remember a fact')
        self.assistant.handle_user_text('note buy milk')
        self.assistant.brain.history.append({'role': 'user', 'content': 'private'})
        self.assistant.handle_user_text('forget everything')
        self.assertEqual(self.assistant.memory.list(), [])
        self.assertEqual(self.assistant.memory.list('note'), [])
        self.assertEqual(len(self.assistant.brain.history), 1)

    def test_timer_spoken_numbers_and_cancellation(self):
        result = self.assistant.handle_user_text('set a timer for twenty five minutes')
        self.assertIn('1500 seconds', result)
        self.assertIn('Timer 1', self.assistant.handle_user_text('list timers'))
        self.assertIn('Cancelled', self.assistant.handle_user_text('cancel timer one'))
        self.assertEqual(self.assistant.desktop.list_timers(), 'No active timers.')

    def test_timer_expiry_delivers_alert(self):
        self.assistant.desktop.start_timer(1)
        identifier = next(iter(self.assistant.desktop.timers))
        timer, _ = self.assistant.desktop.timers[identifier]
        timer.cancel()
        with patch('os.name', 'posix'):
            timer.function()
        self.assertIn('finished', self.assistant.desktop.alerts.get_nowait())

    def test_file_search_uses_configured_folder_only(self):
        folder = self.root/'search'; folder.mkdir()
        (folder/'homework.py').write_text('private code')
        (self.root/'outside.py').write_text('outside')
        settings.save({'file_search_root': str(folder)})
        self.assertIn('homework.py', self.assistant.handle_user_text('find file homework'))
        self.assertNotIn('outside.py', self.assistant.handle_user_text('find file outside'))

    def test_volume_request_uses_fixed_action(self):
        with patch.object(self.assistant.desktop, 'media_key', return_value='sent') as key:
            self.assertEqual(self.assistant.handle_user_text('volume down'), 'sent')
            key.assert_called_once_with('volume down')


class StreamingTests(IsolatedTests):
    def test_streamed_text_is_saved_once(self):
        agent = brain.Brain()
        with patch.object(agent, '_stream_backend', return_value=iter(['Hello ', 'there.'])):
            self.assertEqual(''.join(agent.think_stream('hello', threading.Event())), 'Hello there.')
        self.assertEqual(agent.history[-1]['content'], 'Hello there.')

    def test_forced_local_stream_never_falls_back_to_cloud(self):
        agent = brain.Brain()
        with patch.object(agent, '_stream_backend', side_effect=OSError) as stream:
            list(agent.think_stream('use local hello', threading.Event()))
        self.assertEqual(stream.call_count, 1)
        self.assertEqual(stream.call_args.args[0], 'local')
        self.assertEqual(len(agent.history), 1)

    def test_midstream_failure_does_not_repeat_answer_from_other_backend(self):
        agent = brain.Brain()
        def broken(*args):
            yield 'First sentence.'
            raise OSError()
        with patch.object(agent, '_stream_backend', side_effect=broken) as stream:
            result = ''.join(agent.think_stream('hello', threading.Event()))
        self.assertIn('connection was interrupted', result)
        self.assertEqual(stream.call_count, 1)

    def test_early_stream_failure_can_fall_back(self):
        agent = brain.Brain()
        with patch.object(agent, '_stream_backend', side_effect=[OSError(), iter(['Cloud reply.'])]) as stream:
            self.assertEqual(''.join(agent.think_stream('hello', threading.Event())), 'Cloud reply.')
        self.assertEqual(stream.call_args.args[0], 'cloud')

    def test_cancelled_generation_does_not_commit_history(self):
        agent = brain.Brain(); cancel = threading.Event()
        def chunks(*args):
            yield 'partial'
            cancel.set()
            yield 'late'
        with patch.object(agent, '_stream_backend', side_effect=chunks):
            self.assertEqual(list(agent.think_stream('hello', cancel)), ['partial'])
        self.assertEqual(len(agent.history), 1)

    def test_first_sentence_plays_before_model_finishes(self):
        with patch.object(tts.pygame.mixer, 'get_init', return_value=True):
            speaker = tts.Speaker()
        played = threading.Event()
        def chunks(cancel):
            yield 'First sentence. '
            if not played.wait(1):
                raise AssertionError('Buffered whole answer instead of speaking')
            yield 'Second sentence.'
        def speak(text):
            played.set()
            return True
        with patch.object(speaker, '_speak_segment', side_effect=speak) as segment:
            self.assertTrue(speaker.say_stream(chunks))
        self.assertEqual(segment.call_count, 2)
        self.assertEqual(speaker.spoken_text, 'First sentence. Second sentence.')

    def test_old_cancelled_producer_cannot_revive_on_next_turn(self):
        with patch.object(tts.pygame.mixer, 'get_init', return_value=True):
            speaker = tts.Speaker()
        ready, release = threading.Event(), threading.Event()
        captured = []
        def old(cancel):
            captured.append(cancel); ready.set(); release.wait(2)
            if not cancel.is_set():
                yield 'Late old answer.'
        thread = threading.Thread(target=lambda: speaker.say_stream(old))
        thread.start(); self.assertTrue(ready.wait(1))
        speaker.interrupt(); thread.join(1)
        self.assertFalse(thread.is_alive())
        with patch.object(speaker, '_speak_segment', return_value=True) as speak:
            self.assertTrue(speaker.say('New reply.'))
            release.set()
            self.assertTrue(captured[0].is_set())
            speak.assert_called_once_with('New reply.')

    @unittest.skipUnless(os.name == 'nt', 'Windows speech fallback')
    def test_auto_voice_falls_back_offline_on_edge_failure(self):
        with patch.object(tts.pygame.mixer, 'get_init', return_value=True):
            speaker = tts.Speaker()
        settings.save({'tts_backend': 'auto'})
        async def fail(text):
            raise OSError('network unavailable')
        with patch.object(speaker, '_generate_audio', side_effect=fail), patch.object(speaker, '_windows', return_value=True) as offline:
            self.assertTrue(speaker.say('Hello.'))
        offline.assert_called_once_with('Hello.')


class AudioAndScreenTests(IsolatedTests):
    def test_saved_device_reaches_every_input_stream(self):
        settings.save({'input_device': 7})
        with patch.object(audio.sd, 'InputStream') as stream:
            audio.input_stream()
        self.assertEqual(stream.call_args.kwargs['device'], 7)

    def test_microphone_recording_requires_explicit_destination(self):
        stream = Mock(); stream.__enter__ = Mock(return_value=stream); stream.__exit__ = Mock()
        stream.read.return_value = (bytes(1600), False)
        with patch.object(audio, 'input_stream', return_value=stream), patch.object(audio.time, 'monotonic', side_effect=[0, 0, 1]):
            result = audio.diagnose(seconds=.1)
        self.assertEqual(result['peak_rms'], 0)
        self.assertFalse(list(self.root.glob('*.wav')))

    def test_keyboard_wake_does_not_open_microphone(self):
        event = threading.Event(); event.set()
        with patch.object(wake, 'input_stream') as stream:
            self.assertTrue(wake.wait_for_wake(Mock(), event, threading.Event()))
        stream.assert_not_called()

    def test_local_phrase_wakes_and_releases_microphone(self):
        rec = Mock(); rec.AcceptWaveform.return_value = False
        rec.PartialResult.return_value = json.dumps({'partial': 'hey jarvis'})
        stream = Mock(); stream.__enter__ = Mock(return_value=stream); stream.__exit__ = Mock()
        stream.read.return_value = (bytes(1600), False)
        with patch('vosk.KaldiRecognizer', return_value=rec), patch.object(wake, 'input_stream', return_value=stream):
            self.assertTrue(wake.wait_for_wake(Mock(), threading.Event(), threading.Event()))
        stream.__exit__.assert_called_once()

    def test_screen_is_not_captured_without_configured_vision(self):
        with patch('PIL.ImageGrab.grab') as grab:
            self.assertIn('vision model', screen.explain_screen(Mock()))
        grab.assert_not_called()

    def test_local_screen_request_does_not_use_cloud_or_save_image(self):
        from PIL import Image
        settings.save({'vision_model': 'test-vision'})
        agent = Mock(); agent.ollama_url = 'http://localhost:11434'
        agent._answer_text.side_effect = lambda text: text
        response = Mock(is_redirect=False); response.json.return_value = {'message': {'content': 'An editor.'}}
        with patch('PIL.ImageGrab.grab', return_value=Image.new('RGB', (16, 16))), patch.object(screen.requests.Session, 'post', return_value=response) as post:
            self.assertEqual(screen.explain_screen(agent), 'An editor.')
        self.assertEqual(post.call_args.kwargs['json']['model'], 'test-vision')
        agent.client.chat.completions.create.assert_not_called()
        self.assertFalse(list(self.root.glob('*.jpg')))

    def test_interruption_audio_prefix_is_fed_into_next_recognition(self):
        listener = object.__new__(stt.Listener)
        listener.prefix = deque(); listener.rec = Mock()
        listener.rec.AcceptWaveform.return_value = True
        listener.rec.Result.return_value = json.dumps({'text': 'actually make that five minutes'})
        listener.rec.FinalResult.return_value = '{}'
        prefix = bytes(1600); listener.feed_prefix([prefix])
        stream = Mock(); stream.__enter__ = Mock(return_value=stream); stream.__exit__ = Mock()
        with patch.object(stt, 'input_stream', return_value=stream):
            self.assertIn('actually', listener.listen())
        stream.read.assert_not_called()
        listener.rec.AcceptWaveform.assert_called_once_with(prefix)

    def test_invalid_settings_are_not_saved(self):
        with self.assertRaises(ValueError):
            settings.save({'silence_seconds': -1})
        self.assertFalse((self.root/'settings.json').exists())


class PackagingTests(unittest.TestCase):
    def test_build_staging_never_copies_private_config_or_models(self):
        from scripts.build_windows import stage
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'source'; root.mkdir(); (root/'jarvis').mkdir()
            (root/'jarvis'/'config.py').write_text('SECRET = "private"')
            (root/'jarvis'/'models').mkdir(); (root/'jarvis'/'models'/'private.bin').write_text('private')
            (root/'jarvis'/'main.py').write_text('pass')
            (root/'config.example.py').write_text('PUBLIC = True')
            (root/'run_jarvis_face.py').write_text('pass')
            destination = Path(temp)/'stage'
            stage(root, destination)
            self.assertEqual((destination/'jarvis'/'config.py').read_text(), 'PUBLIC = True')
            self.assertFalse((destination/'jarvis'/'models').exists())


if __name__ == '__main__':
    unittest.main()
