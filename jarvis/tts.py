import asyncio
import os
import time
import edge_tts
import pygame
from jarvis.config import TTS_VOICE, CACHE_DIR

class Speaker:
    def __init__(self):
        # Initialize pygame mixer for audio playback
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        self.temp_file = os.path.join(CACHE_DIR, "speech.mp3")

    async def _generate_audio(self, text: str):
        """Internal async method to generate MP3 from edge-tts."""
        communicate = edge_tts.Communicate(text, TTS_VOICE)
        await communicate.save(self.temp_file)

    def say(self, text: str):
        """Speak the given text out loud using calm British voice."""
        print(f"JARVIS: {text}")

        try:
            # Generate the voice audio
            asyncio.run(self._generate_audio(text))

            # Load and play using pygame
            pygame.mixer.music.load(self.temp_file)
            pygame.mixer.music.play()

            # Wait for finish (blocking so we don't clobber next speech or overlap)
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)

            pygame.mixer.music.unload()

        except Exception as e:
            print(f"[Speaker Error] {e}")
            # Fallback simple print if audio fails
            pass

    def stop(self):
        pygame.mixer.music.stop()
        pygame.mixer.quit()
