"""Playback-reference echo reduction; no audio is recorded to disk.

Delay estimation and a normalized block adaptive FIR model subtract correlated
speaker audio. Double-talk freezes adaptation. This is experimental room AEC,
not a guarantee against every loudspeaker/driver/room combination.
"""
import threading
import time

import numpy as np


class PlaybackReference:
    def __init__(self, rate=16000):
        self.rate = rate
        self.lock = threading.Lock()
        self.samples = np.zeros(0)
        self.started = 0.0
        self.generation = 0
        self.available = False

    def start(self, samples, when=None):
        with self.lock:
            self.samples = np.asarray(samples, dtype=float).copy()
            self.started = time.monotonic() if when is None else when
            self.generation += 1
            self.available = bool(self.samples.size)

    def clear(self):
        with self.lock:
            self.available = False
            self.samples = np.zeros(0)

    def window(self, end, count):
        with self.lock:
            if not self.available:
                return None, self.generation
            finish = int(round((end - self.started) * self.rate))
            begin = finish - count
            result = np.zeros(count)
            lo, hi = max(0, begin), min(len(self.samples), finish)
            if hi > lo:
                result[lo-begin:hi-begin] = self.samples[lo:hi]
            return result, self.generation


class EchoCanceller:
    def __init__(self, reference, threshold=.008, taps=1024):
        self.reference = reference
        self.threshold = threshold
        self.taps = taps
        self.max_delay = int(reference.rate * .35)
        self.weights = np.zeros(taps)
        self.generation = -1
        self.delay = 0
        self.blocks = 0
        self.status = 'learning'

    def process(self, raw, end=None):
        mic = np.frombuffer(raw, dtype=np.int16).astype(float) / 32768
        if not len(mic):
            return b'', False
        history, generation = self.reference.window(
            time.monotonic() if end is None else end,
            len(mic) + self.max_delay + self.taps)
        if history is None:
            self.status = 'unavailable'
            return bytes(len(raw)), False  # No reference: fail closed.
        if generation != self.generation:
            self.weights.fill(0)
            self.generation, self.blocks, self.delay = generation, 0, 0
        n = len(mic)
        # Correlate a bounded 350ms history with this microphone block.
        energies = np.convolve(history * history, np.ones(n), mode='valid')
        dots = np.correlate(history, mic, mode='valid')
        scores = np.abs(dots) / np.sqrt(energies * (mic @ mic) + 1e-12)
        best = int(np.argmax(scores))
        coherence = float(scores[best])
        if coherence > .5:
            self.delay = len(history) - n - best
        finish = len(history) - self.delay
        begin = finish - n
        padded = np.pad(history, (self.taps, 0))
        windows = np.lib.stride_tricks.sliding_window_view(padded, self.taps)[begin+1:finish+1, ::-1]
        if windows.shape[0] != n:
            return bytes(len(raw)), False
        if self.blocks == 0 and coherence > .5:
            x = windows[:, 0]
            self.weights[0] = float(x @ mic) / (float(x @ x) + 1e-9)
        predicted = windows @ self.weights
        residual = mic - predicted
        raw_energy = float(mic @ mic) + 1e-12
        residual_energy = float(residual @ residual)
        # Sample-normalized adaptation learns reflections over a 64ms FIR tail.
        # Freeze the learned room response when independent speech dominates.
        if coherence > .75 and residual_energy < raw_energy * .6:
            for i in range(n):
                x = windows[i]
                error = mic[i] - x @ self.weights
                self.weights += .35 * error * x / (float(x @ x) + 1e-9)
            residual = mic - windows @ self.weights
            residual_energy = float(residual @ residual)
        self.blocks += 1
        self.status = 'active' if coherence > .5 else 'listening'
        # Do not feed a recognizer near-pure playback, including before convergence.
        near = (np.sqrt(residual_energy/n) >= self.threshold and coherence < .88
                and not (coherence > .65 and residual_energy < raw_energy*.25)
                and (self.blocks > 2 or coherence < .5))
        if not near:
            return bytes(len(raw)), False
        return np.clip(residual * 32768, -32768, 32767).astype(np.int16).tobytes(), True
