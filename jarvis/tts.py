"""Sentence-streamed, cancellable speech with an offline Windows fallback."""
import asyncio
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid

import edge_tts
import pygame
from jarvis.config import TTS_VOICE, CACHE_DIR
from jarvis import settings
from jarvis.echo import PlaybackReference


def split_sentences(buffer, final=False):
    parts = []
    while True:
        match = re.search(r'[.!?](?:["\x27])?(?:\s+|$)|\n+', buffer)
        if match:
            end = match.end()
        elif len(buffer) >= 180:
            end = buffer.rfind(' ', 0, 180)
            end = end if end > 0 else 180
        else:
            break
        part, buffer = buffer[:end].strip(), buffer[end:].lstrip()
        if part:
            parts.append(part)
    if final and buffer.strip():
        parts.append(buffer.strip()); buffer = ''
    return parts, buffer


class Speaker:
    def __init__(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error:
            pass  # Windows speech can still work without a pygame output device.
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        self.temp_file = os.path.join(CACHE_DIR, 'speech-' + uuid.uuid4().hex + '.mp3')
        self.active = threading.Event()
        self.playing = threading.Event()
        self.interrupted = threading.Event()
        self.closed = threading.Event()
        self.spoken_text = ''
        self.last_backend = None
        self.last_playback_ended = None
        self._speech_lock = threading.Lock()
        self._turn_cancel = threading.Event()
        self.reference = PlaybackReference()
        self.echo_status = 'waiting'

    async def _generate_audio(self, text):
        await edge_tts.Communicate(text, os.getenv('JARVIS_TTS_VOICE', TTS_VOICE)).save(self.temp_file)

    async def _prepare(self, text):
        task = asyncio.create_task(self._generate_audio(text))
        started = time.monotonic()
        try:
            while not task.done():
                if self.interrupted.is_set() or self.closed.is_set():
                    return False
                if time.monotonic() - started > 12:
                    raise TimeoutError('Voice synthesis timed out')
                await asyncio.sleep(.02)
            await task
            return not (self.interrupted.is_set() or self.closed.is_set())
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def interrupt(self):
        if not self.active.is_set():
            return False
        self.interrupted.set()
        self._turn_cancel.set()
        return True

    def _cancelled(self):
        return self.interrupted.is_set() or self.closed.is_set()

    def wait_for_quiet(self):
        """Allow the final speaker echo to decay before opening microphone input."""
        if self.last_playback_ended is None:
            return
        remaining = settings.get('speaker_tail_seconds') - (time.monotonic() - self.last_playback_ended)
        if remaining > 0:
            self.closed.wait(remaining)

    def _process(self, args, text, **options):
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), **options)
        try:
            process.stdin.write(text)
            process.stdin.close()
            started = time.monotonic()
            while process.poll() is None:
                if self._cancelled() or time.monotonic()-started > 90:
                    process.terminate()
                    process.wait(timeout=3)
                    return False
                time.sleep(.02)
            return process.returncode == 0 and not self._cancelled()
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=3)

    def _windows(self, text):
        if os.name != 'nt':
            raise RuntimeError('Windows speech is unavailable on this OS')
        output = str(Path(self.temp_file).with_suffix('.wav'))
        script = ("$ErrorActionPreference='Stop'; "
                  "[Console]::InputEncoding=[System.Text.Encoding]::UTF8; "
                  "Add-Type -AssemblyName System.Speech; "
                  "$voice=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "try {$voice.SetOutputToWaveFile($env:JARVIS_SPEECH_FILE); "
                  "$voice.Speak([Console]::In.ReadToEnd())} finally {$voice.Dispose()}")
        self.last_backend = 'windows'
        try:
            if not self._process(['powershell.exe', '-NoProfile', '-NonInteractive',
                                  '-WindowStyle', 'Hidden', '-Command', script], text,
                                  env={**os.environ, 'JARVIS_SPEECH_FILE': output}):
                return False
            return self._play_file(output)
        finally:
            Path(output).unlink(missing_ok=True)

    def _play_file(self, filename=None):
        loaded = False
        try:
            if self._cancelled():
                return False
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            filename = filename or self.temp_file
            pygame.mixer.music.load(filename)
            loaded = True
            if self._cancelled():
                return False
            try:
                import numpy as np
                audio = pygame.sndarray.array(pygame.mixer.Sound(filename)).astype(float)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                rate, bits, _ = pygame.mixer.get_init()
                audio /= float(2 ** (abs(bits)-1))
                positions = np.arange(int(len(audio)*16000/rate)) * rate/16000
                samples = np.interp(positions, np.arange(len(audio)), audio)
                self.reference.start(samples)
                self.echo_status = 'learning'
            except Exception:
                self.reference.clear()
                self.echo_status = 'unavailable: keyboard stop available'
            pygame.mixer.music.play()
            self.playing.set()
            while pygame.mixer.music.get_busy():
                if self._cancelled():
                    return False
                time.sleep(.02)
            return not self._cancelled()
        finally:
            if self.playing.is_set():
                self.last_playback_ended = time.monotonic()
            self.playing.clear()
            self.reference.clear()
            if loaded:
                try:
                    pygame.mixer.music.stop()
                    pygame.mixer.music.unload()
                except pygame.error:
                    pass

    def _speak_segment(self, text):
        backend = settings.get('tts_backend')
        try:
            if backend == 'windows':
                return self._windows(text)
            if backend == 'piper':
                executable = shutil.which('piper')
                model = settings.get('piper_model')
                if not executable or not Path(model).is_file():
                    raise RuntimeError('Install piper-tts and select an existing voice model')
                if not self._process([executable, '--model', model, '--output_file', self.temp_file], text):
                    return False
                self.last_backend = 'piper'
            else:
                if not asyncio.run(self._prepare(text)):
                    return False
                self.last_backend = 'edge'
            return self._play_file()
        except Exception as error:
            print('[Voice]', type(error).__name__)
            if backend == 'auto' and not self._cancelled() and os.name == 'nt':
                try:
                    return self._windows(text)
                except Exception as fallback_error:
                    print('[Offline voice]', type(fallback_error).__name__)
            return False
        finally:
            Path(self.temp_file).unlink(missing_ok=True)

    def say(self, text):
        return self.say_stream(lambda cancel: iter([text]))

    def say_stream(self, source, on_text=None):
        """Generate text in a bounded producer; play each sentence as it arrives."""
        with self._speech_lock:
            if self.closed.is_set():
                return False
            self.interrupted.clear()
            cancel = threading.Event()
            self._turn_cancel = cancel
            self.active.set()
            self.spoken_text = ''
            sentences = queue.Queue(maxsize=4)
            done = threading.Event()
            failed = threading.Event()
            def put(sentence):
                while not cancel.is_set() and not self.closed.is_set():
                    try:
                        sentences.put(sentence, timeout=.05)
                        return
                    except queue.Full:
                        continue
            def produce():
                buffer, accumulated = '', ''
                try:
                    for token in source(cancel):
                        if cancel.is_set() or self.closed.is_set():
                            break
                        accumulated += token
                        if on_text:
                            on_text(accumulated)
                        buffer += token
                        ready, buffer = split_sentences(buffer)
                        for sentence in ready:
                            put(sentence)
                    if not cancel.is_set() and not self.closed.is_set():
                        ready, _ = split_sentences(buffer, final=True)
                        for sentence in ready:
                            put(sentence)
                except Exception as error:
                    print('[Reply stream]', type(error).__name__)
                    failed.set()
                finally:
                    done.set()
            producer = threading.Thread(target=produce, name='jarvis-reply-stream', daemon=True)
            producer.start()
            try:
                while not self._cancelled():
                    try:
                        sentence = sentences.get(timeout=.05)
                    except queue.Empty:
                        if done.is_set():
                            return not failed.is_set()
                        continue
                    if sentence == '__sleep__':
                        return True
                    if not self._speak_segment(sentence):
                        self.interrupted.set()
                        return False
                    self.spoken_text += (' ' if self.spoken_text else '') + sentence
                return False
            finally:
                cancel.set()  # A later utterance never revives an old producer.
                producer.join(timeout=.2)
                self.playing.clear()
                self.active.clear()

    def stop(self):
        self.closed.set()
        self.interrupted.set()
        self._turn_cancel.set()
