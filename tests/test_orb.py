import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import unittest
from unittest.mock import Mock, patch
import pygame
from jarvis.face import FaceState, FaceWindow


class OrbTests(unittest.TestCase):
    def setUp(self):
        self.window = FaceWindow(FaceState(), demo=True)

    def tearDown(self):
        pygame.display.quit()

    def test_all_states_render(self):
        for state in ('starting','idle','listening','thinking','speaking','error'):
            self.window.draw(1.2, force_mode=state)
        self.assertEqual(self.window.renderer.surface.get_size(), (760,820))

    def test_real_playback_drives_speaking_state(self):
        self.window.mode = 'thinking'
        with patch.object(pygame.mixer,'get_init',return_value=(44100,-16,2)), patch.object(pygame.mixer.music,'get_busy',return_value=True):
            self.assertEqual(self.window.current_mode(), 'speaking')
        with patch.object(pygame.mixer,'get_init',return_value=None):
            self.assertEqual(self.window.current_mode(), 'thinking')

    def test_wake_palette_and_close_events(self):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_SPACE))
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_t))
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.window.run(seconds=1)
        self.assertTrue(self.window.state.wake.is_set())
        self.assertTrue(self.window.state.stop.is_set())
        self.assertTrue(self.window.renderer.amber)

    def test_space_interrupts_active_reply_instead_of_waking(self):
        speaker = Mock()
        speaker.interrupt.return_value = True
        self.window.state.speaker = speaker
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_SPACE))
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.window.run(seconds=1)
        speaker.interrupt.assert_called()
        self.assertFalse(self.window.state.wake.is_set())


if __name__ == '__main__':
    unittest.main()
