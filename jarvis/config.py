"""Configuration. Private credentials belong in environment variables."""
import os
from pathlib import Path

BASE_DIR = str(Path(__file__).resolve().parents[1])
MODEL_DIR = os.getenv("JARVIS_STT_MODEL", str(Path(BASE_DIR)/"jarvis"/"models"/"vosk-model-small-en-us-0.15"))
CACHE_DIR = str(Path(BASE_DIR)/"cache")
os.makedirs(CACHE_DIR, exist_ok=True)

LLM_BASE_URL = os.getenv("JARVIS_CLOUD_URL", "http://127.0.0.1:31415/v1")
LLM_API_KEY = os.getenv("JARVIS_CLOUD_API_KEY", "")
LLM_MODEL = os.getenv("JARVIS_CLOUD_MODEL", "auto")
SYSTEM_PROMPT = """You are Jarvis, a calm British voice assistant.
Keep replies brief, natural, and suitable for speaking aloud. Address the user as sir.
Do not use Markdown formatting. Do not claim you performed actions or accessed
information unless the application actually supplied the result."""

TTS_VOICE = os.getenv("JARVIS_TTS_VOICE", "en-GB-RyanNeural")
SAMPLE_RATE = 16000
CLAP_ENERGY_THRESHOLD = float(os.getenv("JARVIS_CLAP_THRESHOLD", "0.10"))
CLAP_MIN_INTERVAL = 0.12
CLAP_MAX_INTERVAL = 0.65
VAD_SILENCE_DURATION = 1.5
MAX_SPEECH_DURATION = 12.0
