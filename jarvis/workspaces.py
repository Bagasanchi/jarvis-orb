"""User-saved directory shortcuts; recognized text cannot define executables."""
import json
import os
from pathlib import Path
import re
import subprocess

from jarvis import settings


def normalize(name):
    return ' '.join(name.casefold().strip().split())


class Workspaces:
    def __init__(self):
        self.path = settings.data_dir() / 'workspaces.json'

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, name, directory, editor='explorer'):
        name = normalize(name)
        path = Path(directory).expanduser().resolve(strict=True)
        if not name or len(name) > 80 or not path.is_dir():
            raise ValueError('Choose a name and an existing project folder.')
        if editor not in ('explorer', 'vscode', 'godot'):
            raise ValueError('Choose Explorer, VS Code or Godot.')
        values = self.load()
        values[name] = {'directory': str(path), 'editor': editor}
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(values, indent=2), encoding='utf-8')
        temporary.replace(self.path)

    def launch(self, name, editor=None):
        entry = self.load().get(normalize(name))
        if not isinstance(entry, dict):
            return None
        path = Path(entry.get('directory', '')).resolve(strict=True)
        if not path.is_dir():
            return 'The saved project folder is unavailable.'
        selected = editor or entry.get('editor')
        if os.name != 'nt':
            return 'Workspace launching currently requires Windows.'
        if selected == 'explorer':
            executable = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'explorer.exe'
            args = [str(executable), str(path)]
        elif selected == 'vscode':
            candidates = [Path(os.environ.get('LOCALAPPDATA', ''))/'Programs/Microsoft VS Code/Code.exe',
                          Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'Microsoft VS Code/Code.exe']
            executable = next((p for p in candidates if p.is_file()), None)
            if executable is None:
                return 'VS Code was not found in its standard install locations.'
            args = [str(executable), '--new-window', str(path)]
        elif selected == 'godot':
            executable = Path(settings.get('godot_executable'))
            if not executable.is_absolute() or executable.suffix.lower() != '.exe' or not executable.is_file():
                return 'Select your trusted Godot executable in Settings first.'
            if not (path/'project.godot').is_file():
                return 'That folder does not contain project.godot.'
            args = [str(executable), '--editor', '--path', str(path)]
        else:
            return 'Unsupported workspace editor.'
        subprocess.Popen(args, shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return f'Opened {normalize(name)} in {selected}.'

    def dispatch(self, text):
        match = re.fullmatch(r'(?:open|launch) (?:my )?(.+?)(?: in (vs code|vscode|godot|explorer))?[.!?]*', text.strip(), re.I)
        if not match:
            return None
        editor = {'vs code': 'vscode', 'vscode': 'vscode', 'godot': 'godot', 'explorer': 'explorer'}.get((match[2] or '').lower())
        return self.launch(match[1], editor)
