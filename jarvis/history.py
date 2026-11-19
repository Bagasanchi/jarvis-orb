"""Bounded, in-memory conversation display; no chat transcript files."""
import threading


class History:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = []
        self.next_id = 1
        self.version = 0
        self.epoch = 0

    def clear(self):
        with self.lock:
            self.items.clear()
            self.version += 1
            self.epoch += 1
            # Never reuse IDs: callbacks from cleared turns must stay invalid.

    def begin(self, text, source='voice'):
        with self.lock:
            identifier = self.next_id
            self.next_id += 1
            self.items.extend([{'id': identifier, 'role': 'You', 'source': source, 'text': text},
                               {'id': identifier, 'role': 'Jarvis', 'source': '', 'text': ''}])
            self.items = self.items[-200:]
            self.version += 1
            return identifier

    def answer(self, identifier, text, on_update=None):
        with self.lock:
            for item in self.items:
                if item['id'] == identifier and item['role'] == 'Jarvis':
                    item['text'] = text[:20000]
                    self.version += 1
                    if on_update is not None:
                        on_update()
                    return True
            return False

    def snapshot(self):
        with self.lock:
            return self.version, [dict(item) for item in self.items]
