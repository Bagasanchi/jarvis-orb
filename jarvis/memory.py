"""Explicit memories and notes; ordinary conversations are not persisted."""
import sqlite3
from contextlib import contextmanager
from jarvis.settings import data_dir


class Memory:
    def __init__(self, path=None):
        self.path = path or data_dir() / 'memory.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, text, kind='memory'):
        text = text.strip()
        if not text or len(text) > 4000:
            raise ValueError('Use between 1 and 4000 characters.')
        with self.connect() as db:
            return db.execute('INSERT INTO memories (kind,text) VALUES (?,?)', (kind, text)).lastrowid

    def list(self, kind='memory'):
        with self.connect() as db:
            return db.execute('SELECT id,text FROM memories WHERE kind=? ORDER BY id', (kind,)).fetchall()

    def forget(self, identifier):
        with self.connect() as db:
            return db.execute('DELETE FROM memories WHERE id=?', (identifier,)).rowcount > 0

    def clear(self):
        with self.connect() as db:
            db.execute('DELETE FROM memories')

    def context(self):
        rows = self.list()[-20:]
        return '\n'.join(f'- {text}' for _, text in rows)[:6000]
