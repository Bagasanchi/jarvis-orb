"""Local keyboard/mouse approval. Voice and model output cannot approve actions."""
from dataclasses import dataclass, field
import queue
import sys
import threading
import time


@dataclass
class Request:
    message: str
    expires: float
    done: threading.Event = field(default_factory=threading.Event)
    approved: bool = False
    cancel: object = None
    stop: object = None

    def invalid(self):
        return (time.monotonic() >= self.expires
                or (self.cancel is not None and self.cancel.is_set())
                or (self.stop is not None and self.stop.is_set()))


class Confirmations:
    def __init__(self, stop):
        self.stop = stop
        self.requests = queue.Queue(maxsize=1)
        self.lock = threading.Lock()

    def ask(self, message, timeout=60, cancel=None):
        request = Request(message, time.monotonic() + timeout, cancel=cancel, stop=self.stop)
        if request.invalid():
            return False
        with self.lock:
            # A cancelled request may still be waiting for the UI to poll it.
            try:
                previous = self.requests.get_nowait()
            except queue.Empty:
                previous = None
            if previous is not None and not previous.done.is_set() and not previous.invalid():
                self.requests.put_nowait(previous)
                return False
            if previous is not None:
                previous.done.set()
            self.requests.put_nowait(request)
        while not request.done.wait(.05):
            if request.invalid():
                request.approved = False
                request.done.set()
                return False
        return request.approved and not request.invalid()

    @staticmethod
    def decide(request, approved):
        if request.invalid():
            request.approved = False
            request.done.set()
        elif not request.done.is_set():
            request.approved = bool(approved)
            request.done.set()


def console_confirm(message, cancel=None):
    if cancel is not None and cancel.is_set():
        return False
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        result = input(message + '\nType YES to approve: ').strip() == 'YES'
        return result and (cancel is None or not cancel.is_set())
    except (EOFError, KeyboardInterrupt):
        return False
