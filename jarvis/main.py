"""
Jarvis – a local voice assistant that wakes on double-clap.
"""

import argparse
import re
import os
import sys
import signal
import time
import numpy as np
import sounddevice as sd
import pygame

from jarvis.config import SAMPLE_RATE
from jarvis.brain import Brain
from jarvis.tts import Speaker
from jarvis.stt import Listener
from jarvis.weather import get_weather
from jarvis.app_opener import open_app
from jarvis.clap_detector import WakeDetector


class JarvisAssistant:
    def __init__(self):
        self.brain = Brain()
        self.speaker = Speaker()
        self.listener = Listener()
        self.wake = WakeDetector()
        self._running = True
        self._greeting_shown = False


    def shutdown(self):
        print("\n[JARVIS] Signing off.")
        self._running = False
        self.speaker.stop()
        try:
            sd.stop()
        except Exception:
            pass
        pygame.mixer.quit()

    def handle_user_text(self, text: str) -> str:
        """Parse & dispatch the user utterance."""
        lower = text.lower()

        # Weather is fetched only when requested.
        if any(k in lower for k in ("weather", "temperature", "forecast", "will it rain")):
            location = re.search(r"\bin\s+(.+?)[?.!]*$", text, re.I)
            return get_weather(location.group(1).strip() if location else "Ulaanbaatar")

        # Only explicit app-launch requests reach the allowlisted launcher.
        launch = re.match(r"^(?:please\s+)?(?:open|launch|start|run)\s+(.+?)[.!?]*$", text, re.I)
        if launch:
            _, message = open_app(launch.group(1))
            return message

        # Greetings / identity
        if lower in ("hello", "hi", "hey", "good morning", "good afternoon", "good evening",
                     "who are you", "what are you"):
            hour = time.localtime().tm_hour
            greeting = "evening" if hour >= 18 else "afternoon" if hour >= 12 else "morning"
            if lower in ("who are you", "what are you"):
                return "I am Jarvis, your personal voice assistant. I can help you with weather, apps, and general queries."
            return f"Good {greeting}, sir. How may I assist you today?"

        if lower.startswith("command:"):
            return "Arbitrary shell commands are disabled, sir. Ask me to open a supported application instead."

        # General chat → Claude
        return self.brain.think(text)

    def run(self):
        """Clap twice once to wake up, then talk to Jarvis continuously.

        The double-clap is only needed at startup.  After that Jarvis just
        listens and answers, so you can keep asking without clapping again.
        """
        print("[JARVIS] Clap twice to wake me up. (Ctrl+C to quit.)")
        block_ms = 50
        frames_per_block = int(block_ms * SAMPLE_RATE / 1000)

        # Wake phase: wait for a single double-clap.
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16',
                            blocksize=frames_per_block) as stream:
            while self._running:
                try:
                    raw, overflow = stream.read(frames_per_block)
                except Exception:
                    break
                if self.wake.is_double_clap(raw):
                    break

        # Conversation phase: listen and answer, over and over.
        while self._running:
            self._on_woken()

    def _on_woken(self):
        """Wake-up sequence: greet if first time, then listen and respond."""
        print("[JARVIS] You woke me!")

        if not self._greeting_shown:
            greet = 'Hello, sir. How can I help you today?'
            self._greeting_shown = True
            self.speaker.say(greet)

        # Listen for command
        try:
            user_text = self.listener.listen()
        except Exception as e:
            print(f"[STT Error] {e}")
            user_text = ""

        if not user_text:
            self.speaker.say("I didn't catch that, sir. Please try again.")
            return

        answer = self.handle_user_text(user_text)
        self.speaker.say(answer)

    def demo_once(self):
        """Single-turn handoff used by CLI --once flag."""
        print("Listening for your command...")
        text = self.listener.listen()
        if text:
            reply = self.handle_user_text(text)
            self.speaker.say(reply)
            print("[DEMO] Done.")


def main():
    parser = argparse.ArgumentParser(description="Jarvis Voice Assistant")
    parser.add_argument("--once", action="store_true", help="Run a single turn and exit")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    jarvis = JarvisAssistant()
    if args.once:
        jarvis.demo_once()
    else:
        try:
            jarvis.run()
        finally:
            jarvis.shutdown()


if __name__ == "__main__":
    main()
