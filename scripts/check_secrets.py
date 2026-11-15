"""Scan every unique tracked text blob with detect-secrets; never print values."""
import argparse
import subprocess
import tempfile
from pathlib import Path

from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    refs = git('rev-list', '--all').decode().splitlines() if args.history else ['HEAD']
    seen, findings = set(), []
    with tempfile.TemporaryDirectory() as temporary:
        for ref in refs:
            for entry in git('ls-tree', '-rz', ref).split(b'\0'):
                if not entry:
                    continue
                metadata, filename = entry.split(b'\t', 1)
                _, kind, sha = metadata.split()
                if kind != b'blob' or sha in seen:
                    continue
                seen.add(sha)
                content = git('cat-file', 'blob', sha.decode())
                if b'\0' in content:
                    continue
                try:
                    content.decode('utf-8')
                except UnicodeDecodeError:
                    continue
                path = Path(temporary) / 'scan.txt'
                path.write_bytes(content)
                secrets = SecretsCollection()
                with default_settings():
                    secrets.scan_file(str(path))
                for matches in secrets.data.values():
                    for match in matches:
                        findings.append((filename.decode('utf-8', errors='replace'), match.line_number, match.type))
    for filename, line, kind in sorted(set(findings)):
        print(f'{filename}:{line}: {kind} (value withheld)')
    print(f'Inspected {len(seen)} unique blobs; {len(set(findings))} potential secrets.')
    raise SystemExit(1 if findings else 0)


if __name__ == '__main__':
    main()
