"""Animated Jarvis window. Run this file with --demo for a silent preview."""
import argparse
import math
import queue
import threading
import time
import traceback
import subprocess
import sys

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
        self.speaker = None
        self.alerts = None
        self.retry = threading.Event()
        self.paused = threading.Event()

    def is_set(self):
        return self.stop.is_set() or self.paused.is_set()

    def interrupt_speech(self):
        return bool(self.speaker is not None and self.speaker.interrupt())

    def update(self, state, detail="", transcript=None, reply=None):
        self.events.put((state, detail, transcript, reply))


def assistant_worker(state):
    assistant = None
    try:
        from jarvis.main import JarvisAssistant
        from jarvis.wake import wait_for_wake
        from jarvis import settings

        state.update("starting", "Loading speech recognition and AI connections")
        assistant = JarvisAssistant()
        state.speaker = assistant.speaker
        state.alerts = assistant.desktop.alerts

        def speak(text):
            assistant.speak(text)

        def wait():
            state.update('idle', 'Say ' + settings.get('wake_phrase') + ', or press SPACE. F2 opens Settings.')
            while not state.stop.is_set():
                if state.paused.wait(.05):
                    time.sleep(.05)
                    continue
                try:
                    result = wait_for_wake(assistant.listener.model, state.wake, state)
                    if state.paused.is_set():
                        continue
                    return result
                except Exception:
                    state.update('error', 'Microphone unavailable. F2: Settings. SPACE: begin/retry.')
                    if state.wake.wait(.25):
                        return True
            return False

        if not wait():
            return
        if state.stop.is_set():
            return
        state.update("thinking", "Preparing your greeting")
        greeting = 'Hello, sir. How can I help you today?'
        if state.stop.is_set():
            return
        # The display checks actual mixer playback before animating speech.
        state.update("thinking", "Preparing voice", reply=greeting)
        speak(greeting)
        while not state.stop.is_set():
            if state.paused.is_set():
                state.stop.wait(.1)
                continue
            state.update("listening", "Speak naturally. I'll listen again after answering.")
            try:
                text = assistant.listener.listen(stop_event=state)
            except Exception:
                state.update('error', 'Microphone unavailable. F2: choose/test a microphone. SPACE: retry.')
                state.retry.clear()
                while not state.stop.is_set() and not state.retry.wait(.1):
                    pass
                continue
            if state.is_set():
                if state.paused.is_set():
                    continue
                break
            if not text:
                continue
            state.update("thinking", "Choosing an answer", transcript=text, reply="")
            if text.lower().strip(' .!?') in ('go to sleep', 'sleep jarvis', 'stop listening'):
                speak('Standing by.')
                state.wake.clear()
                if not wait():
                    break
                continue
            assistant.respond(text, on_text=lambda answer: state.update('thinking', 'Preparing voice', reply=answer))
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
        self.renderer.footer = 'SPACE  WAKE / STOP    F2  SETTINGS    T  PALETTE    ESC  QUIT'
        self.mode, self.detail = "starting", "Loading your assistant"
        self.transcript = self.reply = ""
        self.started = time.monotonic()
        self.settings_process = None
        self.alert = ''
        self.alert_until = 0

    def consume(self):
        if self.state.alerts is not None:
            while True:
                try:
                    self.alert = self.state.alerts.get_nowait()
                    self.alert_until = time.monotonic() + 15
                except queue.Empty:
                    break
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
                if (self.state.speaker is not None and self.state.speaker.playing.is_set()) or (pygame.mixer.get_init() and pygame.mixer.music.get_busy()):
                    mode = "speaking"
            except pygame.error:
                pass
        return mode

    def draw(self, elapsed, force_mode=None):
        self.consume()
        mode = force_mode or self.current_mode()
        index = {"idle": 0, "listening": 1, "thinking": 2, "speaking": 3}.get(mode, 2)
        self.renderer.subtitle = self.reply if mode == "speaking" else self.detail
        if self.alert and time.monotonic() < self.alert_until:
            self.renderer.subtitle = self.alert
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
                if self.settings_process is not None and self.settings_process.poll() is not None:
                    self.state.paused.clear()
                    self.state.retry.set()
                    self.settings_process = None
                elapsed = time.monotonic()-self.started
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        self.state.stop.set()
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                            self.state.retry.set()
                            if not self.state.interrupt_speech():
                                self.state.wake.set()
                        elif event.key == pygame.K_F2:
                            if self.settings_process is None or self.settings_process.poll() is not None:
                                self.state.paused.set()
                                self.state.interrupt_speech()
                                args = [sys.executable, '--settings'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'jarvis.setup', '--gui']
                                try:
                                    self.settings_process = subprocess.Popen(args,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                                except OSError:
                                    self.state.paused.clear()
                                    self.state.update('error', 'Could not open Settings. Run python -m jarvis.setup.')
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
            self.state.interrupt_speech()
            pygame.display.quit()


def main():
    if '--settings' in sys.argv:
        from jarvis.setup import gui
        gui()
        return
    parser = argparse.ArgumentParser(description="Jarvis orb interface")
    parser.add_argument("--demo", action="store_true", help="Preview without microphone or AI calls")
    parser.add_argument("--seconds", type=float, help="Close a demo automatically")
    parser.add_argument("--screenshot", help="Save the final demo frame")
    args = parser.parse_args()
    if not args.demo:
        from jarvis import settings
        if not (settings.data_dir() / 'settings.json').exists():
            from jarvis.setup import gui
            gui()
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


