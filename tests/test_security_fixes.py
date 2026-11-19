from contextlib import nullcontext
import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from jarvis.brain import Brain
from jarvis.confirmation import Confirmations
from jarvis.face import FaceState
from jarvis.history import History
from jarvis.main import JarvisAssistant
from jarvis.memory import Memory
from jarvis.screen import explain_screen


class ApprovalCancellationTests(unittest.TestCase):
    def test_remote_ollama_denial_precedes_capture(self):
        brain = Mock(ollama_url='http://192.168.1.5:11434')
        confirm = Mock(return_value=False)
        with patch('jarvis.screen.settings.get', return_value='vision'), patch('PIL.ImageGrab.grab') as capture:
            result = explain_screen(brain, confirm=confirm)
        self.assertIn('192.168.1.5:11434', confirm.call_args.args[0])
        self.assertIn('cancelled', result)
        capture.assert_not_called()

    def test_denied_note_aliases_do_not_load_notes(self):
        assistant = object.__new__(JarvisAssistant)
        assistant.confirm = Mock(return_value=False)
        assistant.memory = Mock()
        for command in ('read my notes', 'list notes', 'my notes'):
            self.assertIn('private', assistant._action(command))
        self.assertEqual(assistant.confirm.call_count, 3)
        assistant.memory.list.assert_not_called()

    def test_cancelled_dialog_cannot_be_approved_late(self):
        broker = Confirmations(threading.Event())
        cancel = threading.Event()
        results = []
        worker = threading.Thread(target=lambda: results.append(broker.ask('Delete?', cancel=cancel)))
        worker.start()
        request = broker.requests.get(timeout=1)
        cancel.set()
        broker.decide(request, True)
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results, [False])
        self.assertFalse(request.approved)

    def test_cancelled_queued_dialog_does_not_block_the_next_turn(self):
        broker = Confirmations(threading.Event())
        cancel = threading.Event()
        worker = threading.Thread(target=lambda: broker.ask('Old request', cancel=cancel))
        worker.start()
        # Wait for enqueue without removing the request from the UI queue.
        with broker.requests.not_empty:
            broker.requests.not_empty.wait_for(lambda: bool(broker.requests.queue), timeout=1)
        cancel.set(); worker.join(1)
        results = []
        next_worker = threading.Thread(target=lambda: results.append(broker.ask('New request', timeout=1)))
        next_worker.start()
        request = broker.requests.get(timeout=1)
        self.assertEqual(request.message, 'New request')
        broker.decide(request, True)
        next_worker.join(1)
        self.assertEqual(results, [True])

    def test_cancelled_deletion_stream_preserves_saved_items(self):
        for command in ('forget everything', 'forget 1'):
            with self.subTest(command=command):
                assistant = object.__new__(JarvisAssistant)
                assistant.memory = Mock()
                broker = Confirmations(threading.Event())
                assistant.confirm = broker.ask
                cancel = threading.Event()
                results = []
                worker = threading.Thread(target=lambda: results.extend(assistant.reply_stream(command, cancel)))
                worker.start()
                request = broker.requests.get(timeout=1)
                cancel.set(); broker.decide(request, True); worker.join(1)
                self.assertFalse(worker.is_alive())
                assistant.memory.clear.assert_not_called()
                assistant.memory.forget.assert_not_called()
                self.assertEqual(results, [])

    def test_cancellation_after_approval_still_prevents_capture(self):
        cancel = threading.Event()
        def approve(message):
            cancel.set()
            return True
        with patch.dict(os.environ, {'JARVIS_CLOUD_VISION_MODEL': 'test-vision'}), patch('jarvis.brain.LLM_API_KEY', 'fixture-value'), patch('PIL.ImageGrab.grab') as capture:
            result = explain_screen(Mock(), cloud=True, confirm=approve, cancel=cancel)
        self.assertIn('cancelled', result)
        capture.assert_not_called()

    def test_cancellation_during_encoding_prevents_upload(self):
        cancel = threading.Event()
        image = Mock(); image.convert.return_value = image
        image.save.side_effect = lambda *args, **kwargs: cancel.set()
        brain = Mock()
        with patch.dict(os.environ, {'JARVIS_CLOUD_VISION_MODEL': 'test-vision'}), patch('jarvis.brain.LLM_API_KEY', 'fixture-value'), patch('PIL.ImageGrab.grab', return_value=image):
            result = explain_screen(brain, cloud=True, confirm=lambda message: True, cancel=cancel)
        self.assertIn('cancelled', result)
        brain.client.chat.completions.create.assert_not_called()


class HistoryErasureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'JARVIS_DATA_DIR': self.temp.name})
        self.env.start(); self.addCleanup(self.env.stop)
        self.state = FaceState()
        self.assistant = object.__new__(JarvisAssistant)
        self.assistant.memory = Memory()
        self.assistant.memory.add('test fact')
        self.assistant.memory.add('test note', 'note')
        self.assistant.brain = Brain()
        self.assistant.brain.history += [{'role': 'user', 'content': 'old private request'}]
        self.assistant.history = self.state.history
        self.assistant.on_history_clear = self.state.clear_conversation
        self.assistant.confirm = Mock(return_value=True)
        self.old = self.state.history.begin('old private request')
        self.state.history.answer(self.old, 'old private reply')
        self.state.update('thinking', transcript='old private request', reply='old private reply')

    def test_forget_all_clears_saved_ai_and_visible_history(self):
        self.assistant._action('forget everything')
        self.assertEqual(self.assistant.memory.list(), [])
        self.assertEqual(self.assistant.memory.list('note'), [])
        self.assertEqual(len(self.assistant.brain.history), 1)
        self.assertEqual(self.state.history.snapshot()[1], [])
        self.assertEqual(self.state.events.get_nowait()[2:], ('', ''))
        self.assertTrue(self.state.events.empty())
        callback = Mock()
        self.assertFalse(self.state.history.answer(self.old, 'late reply', on_update=callback))
        callback.assert_not_called()
        self.assertGreater(self.state.history.begin('new request'), self.old)

    def test_denial_preserves_the_visible_transcript(self):
        self.assistant.confirm.return_value = False
        before = self.state.history.snapshot()
        self.assertEqual(self.assistant._action('forget everything'), 'Deletion cancelled.')
        self.assertEqual(self.state.history.snapshot(), before)
        self.assertEqual(len(self.assistant.memory.list()), 1)

    def test_interrupted_delete_response_cannot_restore_old_ai_history(self):
        assistant = self.assistant
        assistant.listener = Mock()
        assistant.speaker = Mock()
        assistant.speaker.spoken_text = ''
        def speak(source, on_text=None):
            list(source(threading.Event()))
            return False
        assistant.speaker.say_stream.side_effect = speak
        with patch('jarvis.speech_session.speech_session', return_value=nullcontext()):
            assistant.respond('forget everything')
        self.assertEqual(len(assistant.brain.history), 1)
        self.assertEqual(self.state.history.snapshot()[1], [])

    def test_old_stream_cannot_commit_after_history_clear(self):
        agent = self.assistant.brain
        def stream(*args):
            yield 'Old answer. '
            agent.clear_history()
            yield 'Late answer.'
        with patch.object(agent, '_stream_backend', side_effect=stream):
            list(agent.think_stream('old private request', threading.Event()))
        self.assertEqual(len(agent.history), 1)

    def test_old_restore_is_rejected_after_clear(self):
        agent = self.assistant.brain
        generation, history = agent._history_generation, list(agent.history)
        agent.clear_history()
        self.assertFalse(agent.restore_history(history, generation))
        self.assertEqual(len(agent.history), 1)
