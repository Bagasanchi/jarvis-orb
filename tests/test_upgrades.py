import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

from jarvis.confirmation import Confirmations
from jarvis.echo import EchoCanceller, PlaybackReference
from jarvis.face import FaceState
from jarvis.history import History
from jarvis import main, screen, settings
from jarvis import face
from jarvis.workspaces import Workspaces


class EchoTests(unittest.TestCase):
    def test_delayed_amplified_playback_is_not_near_speech(self):
        rng = np.random.default_rng(21)
        samples = rng.normal(0, .08, 32000)
        reference = PlaybackReference()
        reference.start(samples, when=10)
        canceller = EchoCanceller(reference)
        # Hardware acoustic delay 90ms, speaker gain 0.6.
        end, delay = 10.7, 1440
        finish = int(round((end-10)*16000)) - delay
        raw = (samples[finish-800:finish] * .6 * 32768).astype(np.int16).tobytes()
        cleaned, near = canceller.process(raw, end=end)
        self.assertFalse(near)
        self.assertEqual(cleaned, bytes(1600))
        self.assertAlmostEqual(canceller.delay, delay, delta=1)

    def test_user_over_playback_remains_in_residual(self):
        rng = np.random.default_rng(22)
        samples = rng.normal(0, .06, 32000)
        reference = PlaybackReference(); reference.start(samples, when=10)
        canceller = EchoCanceller(reference)
        for block in range(4):
            end = 10.5 + block*.05
            finish = int(round((end-10)*16000)) - 960
            echo = samples[finish-800:finish] * .5
            raw = (echo*32768).astype(np.int16).tobytes()
            canceller.process(raw, end=end)
        end = 10.7; finish = int(round((end-10)*16000)) - 960
        user = rng.normal(0, .07, 800)
        raw = ((samples[finish-800:finish]*.5+user)*32768).astype(np.int16).tobytes()
        cleaned, near = canceller.process(raw, end=end)
        self.assertTrue(near)
        output = np.frombuffer(cleaned, dtype=np.int16)/32768
        self.assertGreater(np.corrcoef(output, user)[0, 1], .9)

    def test_no_reference_fails_closed(self):
        canceller = EchoCanceller(PlaybackReference())
        output, near = canceller.process(bytes(1600))
        self.assertEqual(output, bytes(1600))
        self.assertFalse(near)
        self.assertEqual(canceller.status, 'unavailable')

    def test_delayed_room_reflection_is_reduced(self):
        rng = np.random.default_rng(27)
        samples = rng.normal(0, .08, 48000)
        reference = PlaybackReference(); reference.start(samples, when=10)
        canceller = EchoCanceller(reference)
        near_blocks = []
        for block in range(12):
            end = 10.7 + block*.05
            finish = int(round((end-10)*16000)) - 1200
            echo = samples[finish-800:finish]*.6 + samples[finish-800-480:finish-480]*.3
            cleaned, near = canceller.process((echo*32768).astype(np.int16).tobytes(), end=end)
            near_blocks.append(near)
        self.assertFalse(any(near_blocks[4:]))


class ConfirmationTests(unittest.TestCase):
    def test_confirmation_times_out_and_cannot_be_approved_late(self):
        broker = Confirmations(threading.Event())
        self.assertFalse(broker.ask('delete?', timeout=.01))
        request = broker.requests.get_nowait()
        broker.decide(request, True)
        self.assertFalse(request.approved)

    def test_explicit_ui_decision_releases_waiter(self):
        broker = Confirmations(threading.Event())
        result = []
        worker = threading.Thread(target=lambda: result.append(broker.ask('delete?', timeout=1)))
        worker.start()
        request = broker.requests.get(timeout=1)
        broker.decide(request, True)
        worker.join(1)
        self.assertEqual(result, [True])

    def test_delete_all_is_denied_without_approval(self):
        assistant = object.__new__(main.JarvisAssistant)
        assistant.memory = Mock(); assistant.brain = Mock()
        assistant.confirm = Mock(return_value=False)
        self.assertEqual(assistant._action('forget everything'), 'Deletion cancelled.')
        assistant.memory.clear.assert_not_called()

    def test_declined_cloud_screen_never_captures_or_sends(self):
        brain = Mock()
        with patch.dict(os.environ, {'JARVIS_CLOUD_VISION_MODEL': 'vision'}), patch('jarvis.brain.LLM_API_KEY', 'fixture-value'), patch('PIL.ImageGrab.grab') as capture:
            result = screen.explain_screen(brain, cloud=True, confirm=lambda message: False)
        self.assertIn('cancelled', result)
        capture.assert_not_called()
        brain.client.chat.completions.create.assert_not_called()


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {'JARVIS_DATA_DIR': self.temp.name})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def test_voice_can_only_launch_a_saved_name(self):
        projects = Workspaces()
        with patch('jarvis.workspaces.subprocess.Popen') as launch:
            self.assertIsNone(projects.dispatch('open my unknown project'))
        launch.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows project launcher')
    def test_saved_path_stays_one_argument_even_with_metacharacters(self):
        folder = Path(self.temp.name)/'project & example'; folder.mkdir()
        projects = Workspaces(); projects.save('Jarvis', folder, 'explorer')
        with patch('jarvis.workspaces.os.name', 'nt'), patch('jarvis.workspaces.subprocess.Popen') as launch:
            self.assertIn('Opened', projects.dispatch('open my Jarvis'))
        self.assertEqual(launch.call_args.args[0][-1], str(folder.resolve()))
        self.assertFalse(launch.call_args.kwargs['shell'])

    @unittest.skipUnless(os.name == 'nt', 'Windows project launcher')
    def test_shortcut_editor_override_is_allowlisted(self):
        projects = Workspaces(); projects.save('test', self.temp.name, 'explorer')
        with patch('jarvis.workspaces.subprocess.Popen') as launch:
            self.assertEqual(projects.launch('test', 'powershell'), 'Unsupported workspace editor.')
        launch.assert_not_called()


class ConversationTests(unittest.TestCase):
    def test_typed_worker_request_bypasses_microphone_while_muted(self):
        state = FaceState(); state.muted.set(); state.submit('hello from keyboard')
        assistant = Mock()
        assistant.brain.ollama_url = 'http://127.0.0.1:11434'
        assistant.brain.ollama_model = 'test'
        def respond(text, on_text):
            on_text('Typed reply.')
            state.stop.set()
            return True
        assistant.respond.side_effect = respond
        with patch('jarvis.main.JarvisAssistant', return_value=assistant), patch('jarvis.status.ServiceStatus.check'):
            face.assistant_worker(state)
        assistant.listener.listen.assert_not_called()
        assistant.speak.assert_not_called()
        self.assertEqual(state.history.snapshot()[1][-1]['text'], 'Typed reply.')

    def test_stale_stream_cannot_replace_a_newer_turn(self):
        history = History()
        first = history.begin('old question')
        second = history.begin('new question', 'typed')
        history.answer(second, 'new answer')
        history.answer(first, 'late old answer')
        self.assertEqual(history.snapshot()[1][-1]['text'], 'new answer')

    def test_history_is_bounded(self):
        history = History()
        for _ in range(150):
            history.begin('hello')
        self.assertEqual(len(history.snapshot()[1]), 200)

    def test_typed_input_interrupts_listening_and_works_while_muted(self):
        state = FaceState(); state.muted.set()
        self.assertTrue(state.submit('hello'))
        self.assertEqual(state.inputs.get_nowait(), 'hello')
        self.assertTrue(state.muted.is_set())

    def test_oversized_input_is_rejected(self):
        state = FaceState()
        self.assertFalse(state.submit('x'*4001))
        self.assertTrue(state.inputs.empty())


class StatusTests(unittest.TestCase):
    def test_local_probe_does_not_send_prompts_or_probe_cloud(self):
        from jarvis.status import ServiceStatus
        assistant = Mock()
        assistant.brain.ollama_url = 'http://127.0.0.1:11434'
        assistant.brain.ollama_model = 'test'
        probe = ServiceStatus(assistant, threading.Event())
        response = Mock(); response.json.return_value = {'models': [{'name': 'test'}]}
        with patch('jarvis.status.requests.get', return_value=response) as get:
            probe.check()
        self.assertEqual(probe.local, 'ready')
        get.assert_called_once_with('http://127.0.0.1:11434/api/tags', timeout=(1, 2))
        assistant.brain.client.chat.completions.create.assert_not_called()

    def test_unavailable_local_service_is_visible(self):
        from jarvis.status import ServiceStatus
        assistant = Mock(); assistant.brain.ollama_url = 'http://127.0.0.1:11434'
        probe = ServiceStatus(assistant, threading.Event())
        with patch('jarvis.status.requests.get', side_effect=OSError):
            probe.check()
        self.assertEqual(probe.local, 'unavailable')
