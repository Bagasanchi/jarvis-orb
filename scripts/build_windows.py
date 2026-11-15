"""Build from an allowlisted staging folder; never package private config/data."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def stage(root, destination):
    package = destination / 'jarvis'
    package.mkdir(parents=True)
    for source in (root / 'jarvis').glob('*.py'):
        if source.name != 'config.py':
            shutil.copy2(source, package / source.name)
    shutil.copy2(root / 'config.example.py', package / 'config.py')
    shutil.copy2(root / 'run_jarvis_face.py', destination / 'run_jarvis_face.py')


def main():
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='jarvis-public-build-') as temp:
        destination = Path(temp)
        stage(root, destination)
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
            '--onedir', '--windowed', '--name', 'Jarvis',
            '--collect-all', 'vosk', '--collect-all', 'sounddevice',
            '--collect-all', 'pygame', '--collect-all', 'edge_tts',
            '--hidden-import', 'PIL.ImageGrab', '--hidden-import', 'tkinter',
            '--distpath', str(root/'dist'), '--workpath', str(destination/'build'),
            str(destination/'run_jarvis_face.py')], cwd=destination, check=True)
    shutil.copy2(root / 'README.md', root / 'dist' / 'Jarvis' / 'README.md')


if __name__ == '__main__':
    main()
