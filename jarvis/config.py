"""Public configuration template. No personal keys are bundled."""
import os
import json
from pathlib import Path
from jarvis.settings import data_dir

BASE_DIR = str(Path(__file__).resolve().parents[1])
# Private values stay in ignored data, never in published Python source.
try:
    _private = json.loads((data_dir() / 'credentials.json').read_text(encoding='utf-8'))
    if not isinstance(_private, dict):
        _private = {}
except (OSError, ValueError):
    _private = {}
_legacy_model = Path(BASE_DIR) / 'jarvis' / 'models' / 'vosk-model-small-en-us-0.15'
MODEL_DIR = os.getenv('JARVIS_STT_MODEL', str(_legacy_model if _legacy_model.is_dir() else data_dir() / 'models' / 'vosk-model-small-en-us-0.15'))
CACHE_DIR = str(data_dir() / 'cache')
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
LLM_BASE_URL = os.getenv('JARVIS_CLOUD_URL', _private.get('cloud_url', 'http://127.0.0.1:31415/v1'))
LLM_API_KEY = os.getenv('JARVIS_CLOUD_API_KEY', _private.get('cloud_api_key', ''))
LLM_MODEL = os.getenv('JARVIS_CLOUD_MODEL', _private.get('cloud_model', 'auto'))
SYSTEM_PROMPT = 'You are Jarvis, a concise and helpful personal assistant. Be honest about uncertainty. Never claim to have performed an action unless its tool succeeded.'
TTS_VOICE = os.getenv('JARVIS_TTS_VOICE', 'en-GB-RyanNeural')
SAMPLE_RATE = 16000
VAD_SILENCE_DURATION = 1.0
MAX_SPEECH_DURATION = 30
