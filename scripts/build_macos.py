"""Create an executable-permission-preserving macOS source download on any OS."""
from pathlib import Path
import tempfile
import zipfile

from build_windows import stage


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'dist' / 'Jarvis-macOS.zip'
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        folder = Path(directory) / 'Jarvis'
        stage(root, folder)
        files = sorted(folder.rglob('*.py'))
        extras = ['requirements.txt', 'README.md', 'SECURITY.md', 'Start_Jarvis.command']
        archive = Path(directory) / output.name
        with zipfile.ZipFile(archive, 'w') as bundle:
            for path in files + [root / name for name in extras]:
                relative = path.relative_to(folder) if path in files else Path(path.name)
                entry = zipfile.ZipInfo('Jarvis/' + relative.as_posix())
                entry.create_system = 3
                mode = 0o100755 if path.name == 'Start_Jarvis.command' else 0o100644
                entry.external_attr = mode << 16
                bundle.writestr(entry, path.read_bytes().replace(b'\r\n', b'\n'),
                                compress_type=zipfile.ZIP_DEFLATED)
        archive.replace(output)
    print(output)


if __name__ == '__main__':
    main()
