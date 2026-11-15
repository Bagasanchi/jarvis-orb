"""On-demand screenshot analysis; screenshots stay in memory."""
import base64
import io
import os

import requests
from jarvis import settings


def explain_screen(brain, cloud=False, question='Explain what is on my screen and any visible errors.'):
    model = os.getenv('JARVIS_CLOUD_VISION_MODEL', '') if cloud else settings.get('vision_model')
    if not model:
        return ('Set JARVIS_CLOUD_VISION_MODEL to a vision-capable cloud model first.' if cloud else
                'Choose an installed Ollama vision model in Settings first. Screen analysis uses local AI by default.')
    if cloud:
        from jarvis.brain import LLM_API_KEY
        if not LLM_API_KEY:
            return 'Configure your cloud API key first.'
    from PIL import ImageGrab
    image = ImageGrab.grab()
    image.thumbnail((1280, 1280))
    buffer = io.BytesIO()
    image.convert('RGB').save(buffer, format='JPEG', quality=80)
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    if cloud:
        response = brain.client.chat.completions.create(model=model, max_tokens=400,
            messages=[{'role': 'user', 'content': [{'type': 'text', 'text': question},
                {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + encoded}}]}])
        return brain._answer_text(response.choices[0].message.content)
    response = requests.post(brain.ollama_url + '/api/chat', json={
        'model': model, 'stream': False, 'messages': [
            {'role': 'user', 'content': question, 'images': [encoded]}],
        'options': {'num_predict': 400}}, timeout=(5, 90))
    response.raise_for_status()
    return brain._answer_text(response.json()['message']['content'])
