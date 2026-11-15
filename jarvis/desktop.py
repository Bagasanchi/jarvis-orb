"""Small, explicit desktop actions. No speech is executed as shell code."""
import ctypes
import os
from pathlib import Path
import queue
import re
import threading
import time

from jarvis import settings


def number(text):
    try:
        return float(text)
    except ValueError:
        small = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(), range(20)))
        small.update(dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10))))
        total, group = 0, 0
        words = text.replace('-', ' ').split()
        if not words:
            raise ValueError('No number')
        for word in words:
            if word == 'and':
                continue
            if word in small:
                group += small[word]
            elif word == 'hundred' and group:
                group *= 100
            elif word == 'thousand' and group:
                total += group*1000; group = 0
            else:
                raise ValueError('Unsupported number')
        return float(total + group)


class Desktop:
    def __init__(self):
        self.alerts = queue.SimpleQueue()
        self.timers = {}
        self.lock = threading.Lock()
        self.next_id = 1

    def media_key(self, key):
        if os.name != 'nt':
            return 'Media controls require Windows.'
        codes = {'volume up': 0xAF, 'volume down': 0xAE, 'mute': 0xAD,
                 'play pause': 0xB3, 'next track': 0xB0, 'previous track': 0xB1}
        code = codes[key]
        ctypes.windll.user32.keybd_event(code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(code, 0, 2, 0)
        return f'Sent {key} to Windows.'

    def start_timer(self, seconds):
        if not 1 <= seconds <= 86400:
            return 'Choose a timer between one second and 24 hours.'
        with self.lock:
            identifier = self.next_id
            self.next_id += 1
            def finished():
                with self.lock:
                    self.timers.pop(identifier, None)
                self.alerts.put(f'Timer {identifier} finished.')
                if os.name == 'nt':
                    import winsound
                    winsound.MessageBeep()
            timer = threading.Timer(seconds, finished)
            timer.daemon = True
            self.timers[identifier] = (timer, time.monotonic() + seconds)
            timer.start()
        return f'Timer {identifier} set for {seconds:g} seconds.'

    def cancel_timer(self, identifier):
        with self.lock:
            item = self.timers.pop(identifier, None)
            if item:
                item[0].cancel()
        return f'Cancelled timer {identifier}.' if item else 'That timer was not found.'

    def list_timers(self):
        with self.lock:
            return ' '.join(f'Timer {i}: {max(0, int(deadline-time.monotonic()))} seconds remaining.'
                            for i, (_, deadline) in self.timers.items()) or 'No active timers.'

    def close(self):
        with self.lock:
            for timer, _ in self.timers.values():
                timer.cancel()
            self.timers.clear()

    def search_files(self, query):
        root = Path(settings.get('file_search_root')).expanduser().resolve()
        if not root.is_dir():
            return 'Set an existing file search folder in Settings.'
        query = query.strip().casefold()
        if not query:
            return 'Say a filename to search for.'
        found, count, started = [], 0, time.monotonic()
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('.') and
                       not (Path(directory)/d).is_symlink() and
                       not (hasattr(Path(directory)/d, 'is_junction') and (Path(directory)/d).is_junction())]
            for name in files:
                count += 1
                if query in name.casefold():
                    candidate = Path(directory)/name
                    if not candidate.is_symlink() and candidate.resolve().is_relative_to(root):
                        found.append(str(candidate.relative_to(root)))
                if len(found) >= 5 or count >= 20000 or time.monotonic()-started > 3:
                    return 'Matches: ' + '; '.join(found) if found else 'No matches in the scanned files.'
        return 'Matches: ' + '; '.join(found) if found else 'No matching filenames found.'

    def dispatch(self, text, memory):
        lower = ' '.join(text.lower().strip(' .!?').split())
        media = {'volume up': 'volume up', 'turn the volume up': 'volume up',
                 'volume down': 'volume down', 'turn the volume down': 'volume down',
                 'mute': 'mute', 'mute volume': 'mute', 'toggle mute': 'mute',
                 'play pause': 'play pause', 'pause music': 'play pause',
                 'play music': 'play pause', 'next track': 'next track', 'previous track': 'previous track'}
        if lower in media:
            return self.media_key(media[lower])
        match = re.fullmatch(r'(?:set |start )?(?:a )?timer (?:for )?([\da-z .-]+?)\s+(seconds?|minutes?|hours?)', lower)
        if match:
            multiplier = 3600 if match[2].startswith('hour') else 60 if match[2].startswith('minute') else 1
            try:
                return self.start_timer(number(match[1])*multiplier)
            except ValueError:
                return 'Say a duration such as five minutes or 30 seconds.'
        if lower in ('list timers', 'my timers'):
            return self.list_timers()
        match = re.fullmatch(r'cancel timer ([\da-z -]+)', lower)
        if match:
            try:
                identifier = number(match[1])
                return self.cancel_timer(int(identifier)) if identifier.is_integer() else 'Say a whole timer number.'
            except ValueError:
                return 'Say the timer number.'
        match = re.match(r'^(?:take a note|save a note|note)\s*[:,-]?\s+(.+)$', text, re.I)
        if match:
            return f'Saved note {memory.add(match[1], "note")}.'
        if lower in ('read my notes', 'list notes', 'my notes'):
            return ' '.join(f'Note {i}: {t}' for i, t in memory.list('note')) or 'No saved notes.'
        match = re.match(r'^(?:find file|find a file|search files for)\s+(.+)$', text, re.I)
        if match:
            return self.search_files(match[1].strip(' .!?'))
        return None
