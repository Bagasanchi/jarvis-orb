"""Settings wizard, dependency checks and explicit microphone diagnostics."""
import argparse
import json
from pathlib import Path
import queue
import threading
import urllib.request
import zipfile

from jarvis import settings


def checks():
    import requests
    from jarvis.config import MODEL_DIR
    from jarvis.audio import devices
    result = {'speech_model': (Path(MODEL_DIR) / 'am' / 'final.mdl').is_file()}
    try:
        result['microphones'] = len(devices())
    except Exception as error:
        result['microphones'] = type(error).__name__
    try:
        import os
        response = requests.get(os.getenv('JARVIS_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/') + '/api/tags', timeout=2)
        response.raise_for_status()
        result['ollama_models'] = [m['name'] for m in response.json().get('models', [])]
    except Exception as error:
        result['ollama'] = type(error).__name__
    return result


def download_model():
    """Download the fixed official Vosk model only when the user clicks Download."""
    from jarvis.config import MODEL_DIR
    target = Path(MODEL_DIR).resolve()
    if target.is_dir() and any(target.iterdir()):
        return 'A model already exists; it was preserved.'
    import tempfile
    with tempfile.TemporaryDirectory(dir=settings.data_dir()) as directory:
        archive = Path(directory) / 'model.zip'
        # Fixed HTTPS URL; user input cannot select a URL scheme or host.
        with urllib.request.urlopen('https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip', timeout=30) as response, archive.open('wb') as out:  # nosec B310
            size = 0
            while True:
                chunk = response.read(1024*1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 100*1024*1024:
                    raise ValueError('Model download exceeded its size limit.')
                out.write(chunk)
        extracted = Path(directory) / 'unpacked'
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist()) > 200*1024*1024:
                raise ValueError('Model archive is too large.')
            for member in z.infolist():
                if not (extracted / member.filename).resolve().is_relative_to(extracted.resolve()):
                    raise ValueError('Unsafe archive member.')
            z.extractall(extracted)
        source = extracted / 'vosk-model-small-en-us-0.15'
        if not (source / 'am' / 'final.mdl').is_file():
            raise ValueError('Downloaded archive does not contain the expected model.')
        import shutil
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)
    return 'Speech model installed. Restart Jarvis if it was already open.'


def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from jarvis.audio import devices, diagnose
    root = tk.Tk()
    root.title('Jarvis Settings')
    root.geometry('720x760')
    root.minsize(640, 700)
    container = ttk.Frame(root)
    container.pack(fill='both', expand=True)
    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    frame = ttk.Frame(canvas, padding=20)
    window = canvas.create_window((0, 0), window=frame, anchor='nw')
    frame.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
    root.bind('<MouseWheel>', lambda event: canvas.yview_scroll(-int(event.delta/120), 'units'))
    ttk.Label(frame, text='Jarvis Settings', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Select a microphone, test it, then save. No account is required.').pack(anchor='w', pady=(4, 16))
    saved = settings.load()
    form = ttk.Frame(frame); form.pack(fill='x')
    variables = {}
    try:
        available = devices()
    except Exception:
        available = []
    choices = {'System default': None}
    choices.update({f"{d['index']}: {d['name']} ({d['host']})": d['index'] for d in available})
    current = next((k for k, v in choices.items() if v == saved['input_device']), 'System default')
    def field(label, key, values=None, initial=None):
        row = len(variables)
        ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', padx=(0, 14), pady=5)
        var = tk.StringVar(value=str(saved[key]) if initial is None else initial)
        variables[key] = var
        widget = ttk.Combobox(form, textvariable=var, values=values, state='readonly') if values else ttk.Entry(form, textvariable=var)
        widget.grid(row=row, column=1, sticky='ew', pady=5)
        return widget
    field('Microphone', 'input_device', list(choices), current)
    field('Speech threshold (0–1)', 'speech_threshold')
    field('Silence before reply (seconds)', 'silence_seconds')
    field('Wake phrase', 'wake_phrase')
    field('Audio output', 'audio_output', ['speakers', 'headphones'])
    field('Voice', 'tts_backend', ['auto', 'edge', 'windows', 'piper'])
    field('Piper voice model (optional)', 'piper_model')
    field('Ollama vision model (optional)', 'vision_model')
    field('Filename search folder', 'file_search_root')
    form.columnconfigure(1, weight=1)
    for key, label in [('wake_enabled', 'Enable wake phrase (otherwise press Space)'),
                       ('voice_interrupt', 'Voice stop phrases during speech (headphones mode only)'),
                       ('natural_interrupt', 'Natural interruption (headphones mode only)')]:
        var = tk.BooleanVar(value=saved[key]); variables[key] = var
        ttk.Checkbutton(frame, text=label, variable=var).pack(anchor='w', pady=3)
    def save():
        values = {k: v.get() for k, v in variables.items()}
        values['input_device'] = choices[values['input_device']]
        try:
            settings.save(values)
            status.set('Saved. Audio settings apply on the next listening/speaking turn.')
            return True
        except (ValueError, OSError) as error:
            messagebox.showerror('Settings', str(error))
            return False
    messages = queue.Queue()
    status = tk.StringVar(value='Auto voice uses Edge online, with Windows offline speech as fallback.')
    level = tk.DoubleVar(value=0)
    ttk.Progressbar(frame, variable=level, maximum=100).pack(fill='x', pady=(12, 6))
    ttk.Label(frame, textvariable=status, wraplength=660).pack(anchor='w', pady=8)
    buttons = ttk.Frame(frame); buttons.pack(fill='x', pady=8)
    running = threading.Event()
    def run_task(function):
        if running.is_set():
            return
        running.set()
        status.set('Working…')
        def work():
            try:
                result = function()
                messages.put(('status', result if isinstance(result, str) else json.dumps(result, indent=2)))
            except Exception as error:
                messages.put(('status', f'{type(error).__name__}: Check the selected microphone and Windows microphone permissions.'))
            finally:
                running.clear()
        threading.Thread(target=work, daemon=True).start()
    def test(record=False):
        if save():
            path = settings.data_dir() / 'mic-test.wav' if record else None
            def record_test():
                result = diagnose(level=lambda value: messages.put(('level', min(100, value*1000))), recording=path)
                if path:
                    import winsound
                    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return result
            run_task(record_test)
    ttk.Button(buttons, text='Test microphone', command=lambda: test()).pack(side='left', padx=3)
    ttk.Button(buttons, text='Record & play 3 sec', command=lambda: test(True)).pack(side='left', padx=3)
    ttk.Button(buttons, text='Check setup', command=lambda: run_task(checks)).pack(side='left', padx=3)
    ttk.Button(frame, text='Download English speech model (~40 MB)', command=lambda: run_task(download_model)).pack(anchor='w', pady=4)
    ttk.Button(frame, text='Browse search folder', command=lambda: variables['file_search_root'].set(filedialog.askdirectory() or variables['file_search_root'].get())).pack(anchor='w', pady=4)
    ttk.Button(frame, text='Save settings', command=save).pack(side='left', pady=12)
    ttk.Button(frame, text='Save & close', command=lambda: root.destroy() if save() else None).pack(side='right', pady=12)
    def poll():
        while True:
            try:
                key, value = messages.get_nowait()
                (level if key == 'level' else status).set(value)
            except queue.Empty:
                break
        root.after(50, poll)
    poll()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description='Jarvis setup and microphone diagnostics')
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--list-devices', action='store_true')
    parser.add_argument('--test-mic', action='store_true')
    parser.add_argument('--record', type=Path, help='Explicitly save a three-second microphone test')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(checks(), indent=2))
    elif args.list_devices:
        from jarvis.audio import devices
        print(json.dumps(devices(), indent=2))
    elif args.test_mic or args.record:
        from jarvis.audio import diagnose
        try:
            print(json.dumps(diagnose(recording=args.record), indent=2))
        except Exception as error:
            print('Microphone unavailable:', type(error).__name__, '- choose another device in Settings and check Windows microphone permissions.')
            raise SystemExit(1)
    else:
        gui()


if __name__ == '__main__':
    main()
