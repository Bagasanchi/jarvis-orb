"""Shared microphone selection and short, explicit diagnostics."""
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from jarvis.config import SAMPLE_RATE
from jarvis import settings


def input_stream(**overrides):
    options = dict(samplerate=SAMPLE_RATE, channels=1, dtype='int16',
                   blocksize=int(SAMPLE_RATE * 0.05), device=settings.get('input_device'))
    options.update(overrides)
    if options['device'] is not None and 'extra_settings' not in options:
        try:
            device = sd.query_devices(options['device'], 'input')
            if sd.query_hostapis(device['hostapi'])['name'] == 'Windows WASAPI':
                options['extra_settings'] = sd.WasapiSettings(auto_convert=True)
        except (sd.PortAudioError, ValueError):
            pass
    return sd.InputStream(**options)


def devices():
    hosts = sd.query_hostapis()
    return [{'index': i, 'name': d['name'], 'host': hosts[d['hostapi']]['name'],
             'sample_rate': d['default_samplerate']}
            for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]


def rms(raw):
    samples = np.frombuffer(bytes(raw), dtype=np.int16).astype(float) / 32768
    return float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0


def diagnose(seconds=3, level=None, recording=None):
    """Record only on an explicit diagnostic request; save only if requested."""
    frames = int(SAMPLE_RATE * .05)
    chunks, peak, overflow_count = [], 0.0, 0
    started = time.monotonic()
    with input_stream() as stream:
        while time.monotonic() - started < seconds:
            raw, overflow = stream.read(frames)
            raw = bytes(raw)
            peak = max(peak, rms(raw))
            overflow_count += bool(overflow)
            if recording:
                chunks.append(raw)
            if level:
                level(rms(raw))
    if recording:
        with wave.open(str(Path(recording)), 'wb') as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(SAMPLE_RATE)
            out.writeframes(b''.join(chunks))
    return {'peak_rms': round(peak, 4), 'overflows': overflow_count,
            'speech_detected': peak >= settings.get('speech_threshold')}
