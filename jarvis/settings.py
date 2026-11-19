"""Non-secret, per-user settings. Environment variables override saved values."""
import json
import os
from pathlib import Path
import tempfile
import sys


def data_dir():
    default = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'Jarvis' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent / 'data'
    path = Path(os.getenv('JARVIS_DATA_DIR', str(default)))
    path.mkdir(parents=True, exist_ok=True)
    return path


DEFAULTS = {
    'input_device': None, 'speech_threshold': 0.008, 'silence_seconds': 1.0,
    'wake_phrase': 'hey jarvis', 'wake_enabled': True,
    'voice_interrupt': True, 'natural_interrupt': False,
    'audio_output': 'speakers', 'speaker_tail_seconds': 0.4,
    'echo_cancellation': True, 'godot_executable': '',
    'tts_backend': 'auto', 'piper_model': '',
    'vision_model': '', 'file_search_root': str(Path.home() / 'Documents'),
}


def load():
    try:
        saved = json.loads((data_dir() / 'settings.json').read_text(encoding='utf-8'))
        return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}
    except (OSError, ValueError, AttributeError):
        return dict(DEFAULTS)


def get(key):
    value = os.getenv('JARVIS_' + key.upper())
    if value is None:
        return load()[key]
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return value.lower() not in ('0', 'false', 'off')
    if isinstance(default, float):
        return float(value)
    if key == 'input_device':
        return int(value) if value.isdigit() else value or None
    return value


def save(values):
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError('Unknown setting: ' + ', '.join(sorted(unknown)))
    result = {**load(), **values}
    for key in ('speech_threshold', 'silence_seconds', 'speaker_tail_seconds'):
        result[key] = float(result[key])
    if not 0 < result['speech_threshold'] < 1 or not 0.2 <= result['silence_seconds'] <= 5:
        raise ValueError('Threshold must be between 0 and 1; silence between 0.2 and 5 seconds.')
    if result['tts_backend'] not in ('auto', 'edge', 'windows', 'piper'):
        raise ValueError('Choose auto, edge, windows, or piper for the voice.')
    if result['audio_output'] not in ('speakers', 'headphones'):
        raise ValueError('Choose speakers or headphones for audio output.')
    if not 0 <= result['speaker_tail_seconds'] <= 2:
        raise ValueError('Speaker settling time must be between 0 and 2 seconds.')
    if not str(result['wake_phrase']).strip():
        raise ValueError('Wake phrase cannot be empty.')
    fd, name = tempfile.mkstemp(dir=data_dir(), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(result, out, indent=2)
        os.replace(name, data_dir() / 'settings.json')
    finally:
        Path(name).unlink(missing_ok=True)
