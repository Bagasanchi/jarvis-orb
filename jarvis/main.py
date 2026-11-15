"""Windows voice assistant with explicit actions and local-first conversation."""
import argparse
import re
import threading
import time

from jarvis.brain import Brain
from jarvis.desktop import Desktop, number
from jarvis.memory import Memory
from jarvis.tts import Speaker
from jarvis.stt import Listener
from jarvis.weather import get_weather
from jarvis.app_opener import open_app


class JarvisAssistant:
    def __init__(self):
        self.memory = Memory()
        self.brain = Brain(memory=self.memory)
        self.desktop = Desktop()
        self.speaker = Speaker()
        self.listener = Listener()
        self.stop_event = threading.Event()
        self._running = True

    def shutdown(self):
        self._running = False
        self.stop_event.set()
        self.speaker.stop()
        self.desktop.close()

    def _action(self, text):
        lower = ' '.join(text.lower().strip(' .!?').split())
        match = re.match(r'^remember(?: that)?\s+(.+)$', text, re.I)
        if match:
            return f'Remembered as item {self.memory.add(match[1])}.'
        if lower in ('what do you remember', 'list memories', 'my memories'):
            return ' '.join(f'Item {i}: {t}' for i, t in self.memory.list()) or 'No saved memories.'
        if lower in ('forget everything', 'delete all memories'):
            self.memory.clear()
            self.brain.history = self.brain.history[:1]
            return 'Deleted all saved memories and notes, and cleared this conversation.'
        match = re.fullmatch(r'(?:forget|delete note|forget item) ([\da-z -]+)', lower)
        if match:
            try:
                identifier = number(match[1])
                if not identifier.is_integer():
                    return 'Say a whole item number.'
                return 'Deleted.' if self.memory.forget(int(identifier)) else 'That item was not found.'
            except ValueError:
                return 'Say the item number to delete.'
        desktop = self.desktop.dispatch(text, self.memory)
        if desktop is not None:
            return desktop
        if re.match(r'^(?:use cloud\s+)?(?:explain my screen|what is on my screen|read my screen)(?:[.!?]|$)', text, re.I):
            from jarvis.screen import explain_screen
            return explain_screen(self.brain, cloud=lower.startswith('use cloud '))
        if lower in ('go to sleep', 'sleep jarvis', 'stop listening'):
            return '__sleep__'
        if lower in ('what time is it', 'tell me the time'):
            return time.strftime('It is %I:%M %p.')
        if re.search(r'\b(weather|temperature|forecast)\b|\bwill it rain\b', lower):
            location = re.search(r'\bin\s+(.+?)[?.!]*$', text, re.I)
            return get_weather(location.group(1).strip() if location else 'Ulaanbaatar')
        launch = re.match(r'^(?:please\s+)?(?:open|launch|start|run)\s+(.+?)[.!?]*$', text, re.I)
        if launch:
            return open_app(launch.group(1))[1]
        if lower in ('hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening'):
            return 'Hello, sir. How can I help you today?'
        if lower in ('who are you', 'what are you'):
            return 'I am Jarvis. I can answer questions, control media, set timers, save notes, remember facts, and search filenames.'
        if lower.startswith('command:'):
            return 'Arbitrary shell commands are disabled. Ask for a supported action instead.'
        return None

    def handle_user_text(self, text):
        action = self._action(text.strip())
        return action if action is not None else self.brain.think(text)

    def reply_stream(self, text, cancel):
        try:
            action = self._action(text.strip())
            if action is not None:
                yield action
            else:
                yield from self.brain.think_stream(text, cancel)
        except Exception as error:
            print('[Action unavailable]', type(error).__name__)
            yield 'I could not complete that request. Check Settings and try again.'

    def speak(self, text):
        from jarvis.speech_session import speech_session
        with speech_session(self.speaker, self.listener.model, listener=self.listener):
            return self.speaker.say(text)

    def respond(self, text, on_text=None):
        from jarvis.speech_session import speech_session
        previous_history = list(self.brain.history)
        with speech_session(self.speaker, self.listener.model, listener=self.listener):
            complete = self.speaker.say_stream(lambda cancel: self.reply_stream(text, cancel), on_text=on_text)
        if not complete:
            self.brain.history = previous_history + [
                {'role': 'user', 'content': text},
                {'role': 'assistant', 'content': self.speaker.spoken_text + ' [Reply interrupted.]'}]
        return complete

    def run(self, once=False):
        from jarvis.wake import wait_for_wake
        from jarvis import settings
        wake = threading.Event()
        if once or not settings.get('wake_enabled'):
            wake.set()
        print('Say "' + settings.get('wake_phrase') + '" to begin. Ctrl+C quits.')
        if not wait_for_wake(self.listener.model, wake, self.stop_event):
            return
        self.speak('Hello, sir. How can I help you today?')
        while self._running:
            try:
                text = self.listener.listen(stop_event=self.stop_event)
                if not text:
                    if once:
                        break
                    continue
                if text.lower().strip(' .!?') in ('go to sleep', 'sleep jarvis', 'stop listening'):
                    wake.clear()
                    self.speak('Standing by.')
                    if not wait_for_wake(self.listener.model, wake, self.stop_event):
                        break
                    continue
                self.respond(text)
                if once:
                    break
            except Exception as error:
                print('[Microphone]', type(error).__name__, 'Run python -m jarvis.setup to select and test a microphone.')
                if once:
                    break
                self.stop_event.wait(2)


def main():
    parser = argparse.ArgumentParser(description='Jarvis Voice Assistant')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    assistant = None
    try:
        assistant = JarvisAssistant()
        assistant.run(once=args.once)
    except KeyboardInterrupt:
        pass
    finally:
        if assistant:
            assistant.shutdown()


if __name__ == '__main__':
    main()
