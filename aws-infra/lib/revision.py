"""Non-secret implementation identity for local execution receipts."""
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def source_identity():
    digest = hashlib.sha256()
    paths = [ROOT / 'VERSION', *sorted((ROOT / 'config').glob('*.example.json'))]
    paths += [p for folder in ('bin', 'lib', 'installer') for p in (ROOT / folder).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0' + path.read_bytes())
    tracked = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', '--', 'bin', 'lib', 'installer'], capture_output=True, text=True)
    revision, dirty = None, None
    if tracked.returncode == 0 and tracked.stdout:
        head = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        if head.returncode == 0:
            revision = head.stdout.strip()
        status = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no', '--', '.'], capture_output=True, text=True)
        if status.returncode == 0:
            dirty = bool(status.stdout.strip())
    return {'code_version': (ROOT / 'VERSION').read_text().strip(), 'source_sha256': digest.hexdigest(),
            'git_revision': revision, 'git_tracked_source_dirty': dirty}
