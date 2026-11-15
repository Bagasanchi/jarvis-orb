"""Speech playback that can be interrupted during generation or playback."""
import asyncio
import os
import threading
import time

import edge_tts
import pygame
from jarvis.config import TTS_VOICE, CACHE_DIR


class Speaker:
    def __init__(self):
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        self.temp_file = os.path.join(CACHE_DIR, "speech.mp3")
        self.active = threading.Event()
        self.playing = threading.Event()
        self.interrupted = threading.Event()
        self.closed = threading.Event()

    async def _generate_audio(self, text):
        await edge_tts.Communicate(text, TTS_VOICE).save(self.temp_file)

    async def _prepare(self, text):
        task = asyncio.create_task(self._generate_audio(text))
        started = time.monotonic()
        try:
            while not task.done():
                if self.interrupted.is_set() or self.closed.is_set():
                    return False
                if time.monotonic() - started > 45:
                    raise TimeoutError("Voice synthesis timed out")
                await asyncio.sleep(0.02)
            await task
            return not (self.interrupted.is_set() or self.closed.is_set())
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def interrupt(self):
        """Request cancellation without shutting down future speech."""
        if not self.active.is_set():
            return False
        self.interrupted.set()
        return True

    def say(self, text):
        print(f"JARVIS: {text}")
        if self.closed.is_set():
            return False
        self.interrupted.clear()
        self.active.set()
        loaded = False
        try:
            if not asyncio.run(self._prepare(text)):
                return False
            pygame.mixer.music.load(self.temp_file)
            loaded = True
            if self.interrupted.is_set() or self.closed.is_set():
                return False
            pygame.mixer.music.play()
            self.playing.set()
            while pygame.mixer.music.get_busy():
                if self.interrupted.is_set() or self.closed.is_set():
                    pygame.mixer.music.stop()
                    return False
                time.sleep(0.02)
            return not self.interrupted.is_set()
        except Exception as error:
            print(f"[Speaker Error] {type(error).__name__}: {error}")
            return False
        finally:
            self.playing.clear()
            self.active.clear()
            if loaded:
                try:
                    pygame.mixer.music.stop()
                    pygame.mixer.music.unload()
                except pygame.error:
                    pass

    def stop(self):
        """Final shutdown. For one reply, call interrupt() instead."""
        self.closed.set()
        self.interrupted.set()
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
