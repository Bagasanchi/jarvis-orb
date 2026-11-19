"""Non-blocking local availability checks; never probes cloud with user data."""
import threading

import requests


class ServiceStatus:
    def __init__(self, assistant, stop):
        self.assistant, self.stop = assistant, stop
        self.local = 'checking'
        self.thread = threading.Thread(target=self.run, daemon=True, name='jarvis-service-status')

    def check(self):
        brain = self.assistant.brain
        try:
            response = requests.get(brain.ollama_url + '/api/tags', timeout=(1, 2))
            response.raise_for_status()
            names = [m.get('name') for m in response.json().get('models', [])]
            self.local = 'ready' if brain.ollama_model in names else 'online; model missing'
        except Exception:
            self.local = 'unavailable'

    def run(self):
        while not self.stop.is_set():
            self.check()
            self.stop.wait(15)

    def text(self):
        from jarvis.brain import LLM_API_KEY
        from jarvis import settings
        brain, speaker = self.assistant.brain, self.assistant.speaker
        backend = getattr(brain, 'current_backend', None) or brain.last_backend or 'none yet'
        voice = speaker.last_backend or settings.get('tts_backend')
        return (f'Ollama: {self.local} | Cloud: {"configured (not probed)" if LLM_API_KEY else "not configured"}\n'
                f'AI last attempted: {backend} | Voice: {voice} | Echo: {speaker.echo_status}')
