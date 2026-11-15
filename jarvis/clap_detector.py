"""
Wake detection: listens to mic blocks and fires on a double-clap.

A clap is a sharp broadband transient — very loud for one or two 50 ms
blocks, then quickly quiet.  A single clap produces several consecutive
loud blocks, so a short refractory window after each peak treats them as
one clap.  Two claps inside [CLAP_MIN_INTERVAL, CLAP_MAX_INTERVAL] wake
the assistant.
"""

import time
import numpy as np
from jarvis.config import (
    SAMPLE_RATE,
    CLAP_ENERGY_THRESHOLD,
    CLAP_MIN_INTERVAL,
    CLAP_MAX_INTERVAL,
)

# Refractory period after a detected clap peak (seconds).  Blocks louder
# than the threshold inside this window belong to the same clap.
REFRACTORY = 0.25


class WakeDetector:
    def __init__(self):
        self.last_peak_time = None   # time of the most recent clap peak
        self.refractory_until = 0.0  # ignore loud blocks before this time

    def _rms(self, chunk) -> float:
        """RMS of an int16 PCM block, normalised to [-1, 1]."""
        x = np.frombuffer(bytes(chunk), dtype=np.int16).astype(np.float64) / 32768.0
        return float(np.sqrt(np.mean(x * x))) if x.size else 0.0

    def is_double_clap(self, chunk) -> bool:
        """Feed one int16 mic block (bytes or ndarray). True on wake."""
        energy = self._rms(chunk)
        now = time.monotonic()

        if energy <= CLAP_ENERGY_THRESHOLD:
            return False

        # Still inside the current clap's refractory window -> same clap.
        if now < self.refractory_until:
            return False

        # This is a new clap peak.
        dt = (now - self.last_peak_time) if self.last_peak_time else None
        self.last_peak_time = now
        self.refractory_until = now + REFRACTORY

        if dt is not None and CLAP_MIN_INTERVAL <= dt <= CLAP_MAX_INTERVAL:
            print(f"[Wake] Double clap detected (gap {dt:.2f}s)")
            # Reset so a third clap doesn't immediately re-trigger.
            self.last_peak_time = None
            self.refractory_until = now + 1.5
            return True

        return False
