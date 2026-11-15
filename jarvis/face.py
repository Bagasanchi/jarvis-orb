"""Animated Jarvis window. Run this file with --demo for a silent preview."""
import argparse
import math
import queue
import threading
import time
import traceback

import pygame
from jarvis.orb import OrbRenderer

COLORS = {"idle": (74, 133, 164), "listening": (70, 232, 214),
          "thinking": (181, 151, 255), "speaking": (87, 202, 255),
          "error": (255, 139, 116), "starting": (87, 202, 255)}
LABELS = {"idle": "READY WHEN YOU ARE", "listening": "I'M LISTENING",
          "thinking": "WORKING ON IT", "speaking": "SPEAKING",
          "error": "NEEDS ATTENTION", "starting": "COMING ONLINE"}


class FaceState:
    def __init__(self):
        self.events = queue.SimpleQueue()
        self.stop = threading.Event()
        self.wake = threading.Event()

    def update(self, state, detail="", transcript=None, reply=None):
        self.events.put((state, detail, transcript, reply))


def assistant_worker(state):
    assistant = None
    try:
        from jarvis.main import JarvisAssistant
        from jarvis.config import SAMPLE_RATE
        import sounddevice as sd

        state.update("starting", "Loading speech recognition and AI connections")
        assistant = JarvisAssistant()
        state.update("idle", "Clap twice, or press SPACE to begin")
        # Release the wake microphone before opening speech recognition.
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=int(SAMPLE_RATE * 0.05)) as stream:
            while not state.stop.is_set() and not state.wake.is_set():
                raw, _ = stream.read(int(SAMPLE_RATE * 0.05))
                if assistant.wake.is_double_clap(raw):
                    break
        if state.stop.is_set():
            return
        state.update("thinking", "Preparing your greeting")
        greeting = 'Hello, sir. How can I help you today?'
        if state.stop.is_set():
            return
        # The display checks actual mixer playback before animating speech.
        state.update("thinking", "Preparing voice", reply=greeting)
        assistant.speaker.say(greeting)
        while not state.stop.is_set():
            state.update("listening", "Speak naturally. I'll listen again after answering.")
            text = assistant.listener.listen()
            if state.stop.is_set():
                break
            if not text:
                continue
            state.update("thinking", "Choosing an answer", transcript=text, reply="")
            answer = assistant.handle_user_text(text)
            if state.stop.is_set():
                break
            state.update("thinking", "Preparing voice", reply=answer)
            assistant.speaker.say(answer)
    except Exception as error:
        traceback.print_exc()
        state.update("error", type(error).__name__ + ": " + str(error)[:180])
    finally:
        if assistant is not None:
            try:
                assistant.shutdown()
            except Exception:
                traceback.print_exc()


class FaceWindow:
    """Render on the main thread while speech and AI run on a worker."""
    def __init__(self, state, demo=False):
        self.state = state
        self.demo = demo
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((760, 820), pygame.RESIZABLE)
        pygame.display.set_caption("JARVIS | Orb")
        self.renderer = OrbRenderer(pygame)
        self.mode, self.detail = "starting", "Loading your assistant"
        self.transcript = self.reply = ""
        self.started = time.monotonic()

    def consume(self):
        while True:
            try:
                mode, detail, transcript, reply = self.state.events.get_nowait()
            except queue.Empty:
                break
            self.mode, self.detail = mode, detail
            if transcript is not None:
                self.transcript = transcript
            if reply is not None:
                self.reply = reply

    def current_mode(self):
        mode = self.mode
        if mode == "thinking":
            try:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    mode = "speaking"
            except pygame.error:
                pass
        return mode

    def draw(self, elapsed, force_mode=None):
        self.consume()
        mode = force_mode or self.current_mode()
        index = {"idle": 0, "listening": 1, "thinking": 2, "speaking": 3}.get(mode, 2)
        self.renderer.subtitle = self.reply if mode == "speaking" else self.detail
        self.renderer.draw(elapsed, index)
        if mode in ("starting", "error"):
            surface = self.renderer.surface
            pygame.draw.rect(surface, (3, 9, 15), (120, 668, 520, 45))
            self.renderer.text("COMING ONLINE" if mode == "starting" else "NEEDS ATTENTION",
                               (380, 671), (247, 177, 77), self.renderer.large, center=True)
        w, h = self.screen.get_size()
        scale = min(w/760, h/820)
        size = (max(1, int(760*scale)), max(1, int(820*scale)))
        self.screen.fill((3, 9, 15))
        self.screen.blit(pygame.transform.smoothscale(self.renderer.surface, size),
                         ((w-size[0])//2, (h-size[1])//2))
        pygame.display.flip()

    def run(self, seconds=None, screenshot=None):
        clock = pygame.time.Clock()
        modes = ("idle", "listening", "thinking", "speaking")
        if self.demo:
            self.renderer.footer = "DEMO / NO MICROPHONE     T  PALETTE     ESC  QUIT"
        try:
            while not self.state.stop.is_set():
                elapsed = time.monotonic()-self.started
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        self.state.stop.set()
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                            self.state.wake.set()
                        elif event.key == pygame.K_t:
                            self.renderer.amber = not self.renderer.amber
                if self.demo:
                    self.detail = "Preview: no microphone or AI connection"
                    self.reply = "Hello, sir. How can I help you today?"
                self.draw(elapsed, modes[int(elapsed/3)%4] if self.demo else None)
                if seconds is not None and elapsed >= seconds:
                    if screenshot:
                        pygame.image.save(self.renderer.surface, screenshot)
                    break
                clock.tick(30)
        finally:
            self.state.stop.set()
            pygame.display.quit()


def main():
    parser = argparse.ArgumentParser(description="Jarvis orb interface")
    parser.add_argument("--demo", action="store_true", help="Preview without microphone or AI calls")
    parser.add_argument("--seconds", type=float, help="Close a demo automatically")
    parser.add_argument("--screenshot", help="Save the final demo frame")
    args = parser.parse_args()
    state = FaceState()
    window = FaceWindow(state, demo=args.demo)
    if not args.demo:
        threading.Thread(target=assistant_worker, args=(state,), daemon=True,
                         name="jarvis-assistant").start()
    try:
        window.run(args.seconds if args.demo else None, args.screenshot if args.demo else None)
    except KeyboardInterrupt:
        state.stop.set()
    finally:
        if not args.demo:
            try:
                import sounddevice as sd
                sd.stop()
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()


