#!/usr/bin/env python3
"""Explicit, signed and hash-pinned AWS CLI v2 installation on Control EC2s."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dearmor(text):
    match = re.fullmatch(r'-----BEGIN PGP PUBLIC KEY BLOCK-----\s*(.*?)\s*-----END PGP PUBLIC KEY BLOCK-----\s*', text, re.S)
    if not match:
        raise ValueError('Official armored public key required')
    lines = [s.strip() for s in match[1].splitlines() if s.strip() and ':' not in s and not s.startswith('=')]
    return base64.b64decode(''.join(lines), validate=True)


def verify_signature(archive, signature, key, lock, verifier=None):
    if (sha(archive) != lock['archive_sha256'] or sha(signature) != lock['signature_sha256'] or
        sha(key) != lock['public_key_sha256']):
        raise ValueError('AWS CLI artifact/signature/public-key bytes differ')
    verifier = verifier or shutil.which('gpgv')
    if not verifier:
        raise ValueError('Existing gpgv is required; do not install unreviewed verification tools')
    with tempfile.TemporaryDirectory() as temporary:
        home = Path(temporary); home.chmod(0o700)
        ring = home / 'trusted.gpg';ring.write_bytes(dearmor(Path(key).read_text()))
        result = subprocess.run([verifier, '--homedir', str(home), '--keyring', str(ring),
            '--status-fd', '1', str(signature), str(archive)], capture_output=True, text=True, timeout=60)
    records = [line.split() for line in result.stdout.splitlines()]
    valid = [r for r in records if len(r) > 2 and r[:2] == ['[GNUPG:]', 'VALIDSIG']]
    rejected = {'BADSIG', 'ERRSIG', 'EXPKEYSIG', 'EXPSIG', 'REVKEYSIG', 'KEYEXPIRED', 'SIGEXPIRED', 'KEYREVOKED'}
    if (result.returncode or len(valid) != 1 or valid[0][2] != lock['signer_fingerprint'] or
        any(len(r) > 1 and r[1] in rejected for r in records)):
        raise ValueError('AWS CLI PGP signature/signer verification failed')


def extract_verified(archive, destination):
    """Called only after PGP verification; still refuse traversal and links."""
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Extraction state exists; inspect the previous attempt')
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        for entry in entries:
            path = Path(entry.filename);mode = entry.external_attr >> 16
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'aws' or stat.S_ISLNK(mode):
                raise ValueError('Unexpected AWS CLI archive member')
        destination.mkdir(mode=0o700)
        for entry in entries:
            target = package.extract(entry, destination)
            mode = (entry.external_attr >> 16) & 0o777
            Path(target).chmod(0o755 if entry.is_dir() else (0o755 if mode & 0o111 else 0o644))


def version(binary):
    result = subprocess.run([str(binary), '--version'], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError('AWS CLI binary cannot execute')
    return result.stdout.strip()


def install(runtime):
    if sys.platform != 'linux' or os.geteuid() != 0 or platform.machine() != 'x86_64':
        raise ValueError('Explicit x86_64 Linux EC2 root installation required')
    c = json.loads(Path(runtime).read_text())
    if c['node']['role'] != 'control':
        raise ValueError('AWS CLI stage is limited to Control A/B')
    spec = importlib.util.spec_from_file_location('cli_ec2_identity', ROOT / 'aws-identity.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify(c, module.identity)
    subprocess.run([sys.executable, str(ROOT / 'init-disk.py'), str(runtime), '--check-only'], check=True, capture_output=True)
    lock = json.loads((ROOT / 'aws-cli.lock.json').read_text())
    if (lock['schema'] != 1 or lock['architecture'] != 'x86_64' or not re.fullmatch(r'2\.[0-9]+\.[0-9]+', lock['version']) or
        lock['install_dir'] != '/opt/music-cluster/aws-cli' or lock['bin_dir'] != '/opt/music-cluster/aws-cli-bin' or
        lock['binary'] != lock['install_dir'] + '/v2/' + lock['version'] + '/bin/aws'):
        raise ValueError('Reviewed isolated installation layout required')
    for field in ('archive_url', 'signature_url'):
        expected = 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64-' + lock['version'] + '.zip' + ('.sig' if field == 'signature_url' else '')
        if lock[field] != expected:
            raise ValueError('Version-specific official AWS CLI URL required')
    target, binary = Path(lock['install_dir']), Path(lock['binary'])
    marker = target / '.music-reviewed-lock.json'
    if target.is_symlink() or Path(lock['bin_dir']).is_symlink():
        raise ValueError('Unexpected installation directory link')
    if target.exists():
        if not marker.is_file() or json.loads(marker.read_text()) != lock or not version(binary).startswith('aws-cli/' + lock['version'] + ' '):
            raise ValueError('Existing/partial CLI requires explicit review; no automatic overwrite or upgrade')
        return {'version': lock['version'], 'already_installed': True, 'binary': str(binary)}
    if Path(lock['bin_dir']).exists():
        raise ValueError('Unmanaged CLI bin directory exists')
    cache = Path('/var/cache/music-cluster/aws-cli') / lock['version']
    cache.mkdir(parents=True, exist_ok=True, mode=0o700);cache.chmod(0o700)
    if cache.is_symlink() or cache.resolve() != cache:
        raise ValueError('Unsafe CLI cache path')
    for filename, url, checksum in (
        ('awscliv2.zip', lock['archive_url'], lock['archive_sha256']),
        ('awscliv2.zip.sig', lock['signature_url'], lock['signature_sha256'])):
        path = cache / filename
        if path.is_symlink():raise ValueError('Artifact link is forbidden')
        if not path.exists():
            part = path.with_suffix(path.suffix + '.part')
            if part.exists():raise ValueError('Partial download retained; inspect before retry')
            subprocess.run(['curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https',
                '--connect-timeout', '15', '--max-time', '300', '--silent', '--show-error', url, '-o', str(part)], check=True, capture_output=True)
            if sha(part) != checksum:raise ValueError('Downloaded CLI checksum differs')
            part.rename(path)
        if sha(path) != checksum:raise ValueError('Cached CLI checksum differs')
    verify_signature(cache / 'awscliv2.zip', cache / 'awscliv2.zip.sig', ROOT / 'aws-cli-public.asc', lock)
    intent = cache / 'install-intent.json'
    if intent.exists():raise ValueError('Previous install intent exists; inspect before retry')
    extract_verified(cache / 'awscliv2.zip', cache / 'unpacked')
    intent.write_text(json.dumps({'version': lock['version'], 'archive_sha256': lock['archive_sha256']}))
    subprocess.run(['bash', str(cache / 'unpacked/aws/install'), '--install-dir', str(target),
        '--bin-dir', lock['bin_dir']], check=True, capture_output=True, text=True, timeout=180)
    if not version(binary).startswith('aws-cli/' + lock['version'] + ' '):
        raise ValueError('Installed AWS CLI version differs')
    for path in (target, *target.rglob('*'), Path(lock['bin_dir']), *Path(lock['bin_dir']).iterdir()):
        if path.is_symlink():continue
        os.chown(path, 0, 0);path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    marker.write_text(json.dumps(lock, indent=2) + '\n');marker.chmod(0o644)
    return {'version': lock['version'], 'signature_verified': True, 'sha256_verified': True,
            'binary': str(binary), 'global_cli_or_profiles_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime', required=True)
    args = parser.parse_args();os.umask(0o077)
    try:print(json.dumps(install(args.runtime)))
    except Exception as error:sys.exit('[FAIL] AWS CLI installation blocked (' + type(error).__name__ + '); partial state preserved')
