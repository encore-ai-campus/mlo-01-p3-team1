#!/usr/bin/env python3
"""Install an immutable, opt-in Delta addon without changing Spark's classpath."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('Regular, non-symlink file required')
    return path


def validate_bundle(directory, spark_home, reviewed_lock, connector_lock):
    directory, spark_home = Path(directory), Path(spark_home)
    if directory.is_symlink() or not directory.is_dir(): raise ValueError('Unsafe Delta bundle')
    reviewed_lock, connector_lock = regular(reviewed_lock), regular(connector_lock)
    manifest = json.loads(regular(directory / 'delta.lock.json').read_text())
    if manifest != json.loads(reviewed_lock.read_text()): raise ValueError('Delta bundle differs from reviewed lock')
    if (manifest.get('schema_version') != 1 or manifest.get('spark_version') != '4.1.3' or
        manifest.get('hadoop_version') != '3.4.2' or manifest.get('candidate') != 'io.delta:delta-spark_4.1_2.13:4.3.1' or
        manifest.get('duplicate_class_findings') != 0): raise ValueError('Unreviewed Delta runtime')
    if digest(connector_lock) != manifest['base_connector_lock_sha256']: raise ValueError('Base connector lock changed')
    base = json.loads(connector_lock.read_text())
    if json.loads(regular(spark_home / 'connectors.lock.json').read_text()) != base: raise ValueError('Installed connector lock differs')
    baseline = base['distribution_jars'] + base['jars']
    jar_dir = spark_home / 'jars'
    if jar_dir.is_symlink() or not jar_dir.is_dir(): raise ValueError('Unsafe Spark jar directory')
    if {p.name for p in jar_dir.glob('*.jar')} != {j['filename'] for j in baseline}: raise ValueError('Unexpected Spark classpath')
    for entry in baseline:
        if digest(regular(jar_dir / entry['filename'])) != entry['sha256']: raise ValueError('Existing Spark/connector JAR changed')
    entries = manifest['jars']
    if len(entries) != 9 or len({j['filename'] for j in entries}) != 9: raise ValueError('Nine distinct reviewed Delta additions required')
    if {p.name for p in directory.iterdir()} != {'delta.lock.json', *[j['filename'] for j in entries]}: raise ValueError('Unexpected Delta bundle contents')
    for entry in entries:
        name, sha = entry['filename'], entry['sha256']
        coordinate = entry.get('coordinate', '')
        if (not re.fullmatch(r'[A-Za-z0-9_.-]+\.jar', name) or not re.fullmatch(r'[0-9a-f]{64}', sha) or
            not re.fullmatch(r'[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+', coordinate) or
            coordinate.endswith('-SNAPSHOT') or any(j['filename'] == name for j in baseline)):
            raise ValueError('Invalid/additive-only Delta entry')
        if digest(regular(directory / name)) != sha: raise ValueError('Delta JAR checksum mismatch')
    return manifest


def publish(directory, spark_home, addons, reviewed_lock, connector_lock):
    manifest = validate_bundle(directory, spark_home, reviewed_lock, connector_lock)
    addons = Path(addons)
    if addons.is_symlink() or addons.parent.is_symlink(): raise ValueError('Unsafe addon parent')
    # mkdir(parents=True) applies its mode only to the leaf. With the private
    # installer umask, a newly created intermediate parent would be 0700.
    parent_created = not addons.parent.exists()
    addons.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    if parent_created: addons.parent.chmod(0o755)
    addons.mkdir(exist_ok=True, mode=0o755);addons.chmod(0o755)
    target = addons / digest(reviewed_lock)
    if target.exists() or target.is_symlink():
        validate_bundle(target, spark_home, reviewed_lock, connector_lock)
        return target, False
    with tempfile.TemporaryDirectory(prefix='.delta-staging-', dir=addons) as temporary:
        stage = Path(temporary)
        for name in ['delta.lock.json', *[j['filename'] for j in manifest['jars']]]:
            shutil.copyfile(Path(directory) / name, stage / name);(stage / name).chmod(0o644)
        validate_bundle(stage, spark_home, reviewed_lock, connector_lock)
        stage.chmod(0o755);stage.rename(target)
    return target, True


def guard(runtime):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or os.geteuid() != 0:
        raise ValueError('Ubuntu EC2 amd64/root required')
    text = Path('/etc/os-release').read_text()
    if 'ID=ubuntu\n' not in text or 'VERSION_ID="24.04"' not in text: raise ValueError('Ubuntu 24.04 required')
    if runtime['node']['role'] not in ('spark', 'control'): raise ValueError('Delta target must be Spark or Control')
    for name in ('aws-identity', 'init-disk'):
        spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        if name == 'aws-identity': module.verify(runtime, module.identity)
        else: module.initialize(runtime, check_only=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'install'))
    parser.add_argument('--directory', required=True)
    parser.add_argument('--spark-home', default='/opt/music-cluster/spark')
    parser.add_argument('--reviewed-lock', default=str(ROOT / 'delta.lock.json'))
    parser.add_argument('--connector-lock', default=str(ROOT / 'connectors.lock.json'))
    parser.add_argument('--runtime');parser.add_argument('--source');parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.action == 'install' and not args.execute:
        print(json.dumps({'executed': False, 'action': 'isolated Delta addon installation'}));return
    if args.action == 'validate':
        validate_bundle(args.directory, args.spark_home, args.reviewed_lock, args.connector_lock)
        print(json.dumps({'validated': True, 'additional_jars': 9}));return
    runtime = json.loads(regular(args.runtime).read_text());guard(runtime)
    source = json.loads(regular(args.source).read_text())
    if not re.fullmatch(r'[0-9a-f]{64}', source.get('source_sha256', '')): raise ValueError('Reviewed source identity required')
    target, created = publish(args.directory, args.spark_home, '/opt/music-cluster/spark-addons/delta', args.reviewed_lock, args.connector_lock)
    state = Path('/var/lib/music-cluster/aws-state') / runtime['aws']['generation'] / 'delta' / digest(args.reviewed_lock)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    proof = {'aws': runtime['aws'], 'node': runtime['node']['name'], 'source': source,
             'delta_lock_sha256': digest(args.reviewed_lock), 'addon_directory': str(target),
             'newly_published': created, 'additional_jars': 9, 'base_classpath_unchanged': True,
             'global_spark_config_unchanged': True, 'automatic_activation': False}
    path = state / 'installed.json'
    if path.exists():
        old = json.loads(path.read_text())
        if any(old[k] != proof[k] for k in ('aws', 'node', 'delta_lock_sha256', 'addon_directory')):
            raise ValueError('Existing addon installation identity differs')
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream: json.dump(proof, stream)
    print(json.dumps({'installed': True, 'additional_jars': 9, 'base_classpath_unchanged': True,
                      'global_config_unchanged': True, 'automatic_activation': False}))


if __name__ == '__main__':
    try: main()
    except Exception as error: sys.exit('[FAIL] Delta operation blocked (' + type(error).__name__ + '); existing data preserved')
