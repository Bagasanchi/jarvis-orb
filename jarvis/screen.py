"""On-demand screenshot analysis; screenshots stay in memory."""
import base64
import io
import ipaddress
import os
from urllib.parse import urlsplit

import requests
from jarvis import settings


def explain_screen(brain, cloud=False, question='Explain what is on my screen and any visible errors.', confirm=None, cancel=None):
    if cancel is not None and cancel.is_set():
        return 'Screen analysis cancelled.'
    model = os.getenv('JARVIS_CLOUD_VISION_MODEL', '') if cloud else settings.get('vision_model')
    if not model:
        return ('Set JARVIS_CLOUD_VISION_MODEL to a vision-capable cloud model first.' if cloud else
                'Choose an installed Ollama vision model in Settings first. Screen analysis uses local AI by default.')
    if cloud:
        from jarvis.brain import LLM_API_KEY
        if not LLM_API_KEY:
            return 'Configure your cloud API key first.'
        from jarvis.brain import LLM_BASE_URL
    endpoint = LLM_BASE_URL if cloud else brain.ollama_url
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname
        if (parsed.scheme not in ('http', 'https') or not host or parsed.username is not None
                or '\\' in endpoint or any(c.isspace() for c in endpoint)):
            raise ValueError
        port = parsed.port
    except ValueError:
        return 'Check the screen analysis server address in your settings, sir.'
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == 'localhost'
    if cloud or not local:
        address = f'[{host}]' if ':' in host else host
        if port is not None:
            address += f':{port}'
        if confirm is None or not confirm(f'Shall I send your visible screen to {address} for analysis, sir?'):
            return 'Screen upload cancelled. No screenshot was captured.'
    if cancel is not None and cancel.is_set():
        return 'Screen analysis cancelled.'
    from PIL import ImageGrab
    image = ImageGrab.grab()
    image.thumbnail((1280, 1280))
    buffer = io.BytesIO()
    image.convert('RGB').save(buffer, format='JPEG', quality=80)
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    if cancel is not None and cancel.is_set():
        return 'Screen analysis cancelled.'
    if cloud:
        response = brain.client.chat.completions.create(model=model, max_tokens=400,
            messages=[{'role': 'user', 'content': [{'type': 'text', 'text': question},
                {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + encoded}}]}])
        return brain._answer_text(response.choices[0].message.content)
    with requests.Session() as session:
        session.trust_env = False
        response = session.post(endpoint + '/api/chat', json={
            'model': model, 'stream': False, 'messages': [
                {'role': 'user', 'content': question, 'images': [encoded]}],
            'options': {'num_predict': 400}}, timeout=(5, 90), allow_redirects=False)
    if response.is_redirect:
        return 'The screen analysis server redirected the request. I stopped there, sir.'
    response.raise_for_status()
    return brain._answer_text(response.json()['message']['content'])
