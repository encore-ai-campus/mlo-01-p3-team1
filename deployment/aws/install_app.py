"""Install a reviewed release on the explicitly identified existing EC2 app host.

Input is an owner-only payload prepared by the deployer. Never execute env-file
contents, replace an unrelated app, or start background writers on both Controls.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def execute(argv, *, env=None, user=None, cwd=None, timeout=1800):
    options = {}
    if user:
        account = pwd.getpwnam(user)
        options.update(user=account.pw_uid, group=account.pw_gid, extra_groups=[])
    result = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True,
                            timeout=timeout, **options)
    if result.returncode:
        # Keep raw diagnostics owner-only. No exception/body/secret is sent to SSM output.
        log = Path('/var/log/music-app-install.log')
        log.write_text(result.stdout + '\n' + result.stderr)
        log.chmod(0o600)
        raise RuntimeError('step_failed:' + Path(argv[0]).name)
    return result.stdout


def write(path, value, mode=0o644, group=None):
    path = Path(path)
    new_parent = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if new_parent and group:
        path.parent.chmod(0o750)
        os.chown(path.parent, 0, pwd.getpwnam(group).pw_gid)
    path.write_text(value)
    path.chmod(mode)
    if group:
        os.chown(path, 0, pwd.getpwnam(group).pw_gid)


def environment(path):
    values = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch('[A-Z][A-Z0-9_]*', key) or '\x00' in value:
            raise RuntimeError('invalid_environment_data')
        values[key] = value
    return {**os.environ, **values}


def unit(name, role, release, command, *, writable=True):
    text = f'''[Unit]
Description=Music application {name}
After=network-online.target
Wants=network-online.target
RequiresMountsFor=/var/lib/music-cluster
StartLimitIntervalSec=300
StartLimitBurst=5
[Service]
Type=simple
User={role}
Group={role}
WorkingDirectory={release}
EnvironmentFile=/etc/music-cluster/{role}/application.env
ExecStart={command}
Restart=on-failure
RestartSec=10
TimeoutStopSec=90
KillMode=control-group
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/music-cluster/{role}
[Install]
WantedBy=multi-user.target
'''
    write('/etc/systemd/system/' + name + '.service', text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--skip-initialize', action='store_true', help='Existing initialized generation only; caller must stop and verify old writers first.')
    args = parser.parse_args()
    plan = json.loads((HERE / 'deployment.json').read_text())
    role, node = plan['role'], plan['node']
    if role not in ('control', 'advertising') or not re.fullmatch('[a-z0-9-]+', node):
        raise RuntimeError('unknown_app_role')
    if os.geteuid() != 0 or not os.path.ismount('/var/lib/music-cluster'):
        raise RuntimeError('root_and_mounted_data_required')
    token = urlopen(Request('http://169.254.169.254/latest/api/token', method='PUT',
                    headers={'X-aws-ec2-metadata-token-ttl-seconds':'60'}), timeout=3).read().decode()
    actual = urlopen(Request('http://169.254.169.254/latest/meta-data/instance-id',
                    headers={'X-aws-ec2-metadata-token':token}), timeout=3).read().decode()
    if actual != plan['instance_id']:
        raise RuntimeError('instance_mismatch')
    receipt = Path('/var/lib/music-cluster/aws-state') / plan['generation'] / ('control.json' if role == 'control' else 'application-host.json')
    native = json.loads(receipt.read_text())
    if native['generation'] != plan['generation'] or native['node'] != node:
        raise RuntimeError('generation_or_native_node_mismatch')
    source = HERE / 'app'
    manifest = json.loads((HERE / 'manifest.json').read_text())
    for name, checksum in manifest.items():
        path = source / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(source.resolve()) or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise RuntimeError('release_checksum_mismatch')
    if not args.apply:
        print(json.dumps({'apply':False, 'node':node, 'verified_files':len(manifest)}))
        return
    base = Path('/opt/music-apps') / role
    release = base / 'releases' / plan['release']
    if not release.exists():
        release.parent.mkdir(parents=True, exist_ok=True)
        release.parent.chmod(0o751)
        base.chmod(0o751)
        base.parent.chmod(0o751)
        shutil.copytree(source, release)
        for path in release.rglob('*'):
            path.chmod(0o755 if path.is_dir() else 0o644)
        release.chmod(0o755)
    env_path = Path('/etc/music-cluster') / role / 'application.env'
    write(env_path, (HERE / 'application.env').read_text(), 0o640, role)
    env = environment(env_path)
    data = Path('/var/lib/music-cluster') / role
    for name in ('raw-music', 'weather', 'logs', 'tmp'):
        target = data / name
        target.mkdir(parents=True, exist_ok=True)
        account = pwd.getpwnam(role)
        os.chown(target, account.pw_uid, account.pw_gid)
        target.chmod(0o700)
    # MongoDB's advertised replica-set member name must resolve on the client.
    if role == 'advertising':
        import socket
        expected = plan['mongo_ip']
        try: found = socket.gethostbyname('mongodb')
        except socket.gaierror:
            with open('/etc/hosts', 'a') as handle:
                handle.write('\n' + expected + ' mongodb\n')
        else:
            if found != expected: raise RuntimeError('mongodb_hostname_mismatch')
    execute(['apt-get', 'update', '-qq'])
    packages = ['python3-venv'] + (['nginx'] if role == 'control' else [])
    execute(['apt-get', 'install', '-y', '-qq', *packages],
            env={**os.environ, 'DEBIAN_FRONTEND':'noninteractive'})
    locknames = ['backend/requirements.lock', 'deployment/aws/common-runtime.lock'] if role == 'control' else ['deployment/aws/advertising-runtime.lock']
    digest = hashlib.sha256(b''.join((release / n).read_bytes() for n in locknames)).hexdigest()[:16]
    venv = base / ('venv-' + digest)
    python = '/opt/music-cluster/python/bin/python3.14' if role == 'control' else '/usr/bin/python3'
    if not (venv / '.dependencies-ready').exists():
        execute([python, '-m', 'venv', str(venv)])
        command = [str(venv / 'bin/python'), '-m', 'pip', 'install', '--disable-pip-version-check', '--index-url', 'https://pypi.org/simple']
        for name in locknames: command += ['--requirement', str(release / name)]
        execute(command, env={**os.environ, 'PIP_CONFIG_FILE':'/dev/null'}, timeout=1800)
        write(venv / '.dependencies-ready', digest)
    # Root-owned code/dependencies are readable/executable by the service user.
    # Neither directory contains application.env or other deployment secrets.
    for path in [venv, *venv.rglob('*')]:
        if path.is_symlink(): continue
        executable = path.is_dir() or bool(path.stat().st_mode & 0o111)
        path.chmod(0o755 if executable else 0o644)
    py = str(venv / 'bin/python')
    if role == 'control':
        spark_conf = '/etc/music-cluster/control/spark'
        conf_directory = Path(spark_conf)
        if conf_directory.is_symlink(): raise RuntimeError('unsafe_spark_configuration_directory')
        conf_directory.mkdir(parents=True, exist_ok=True)
        conf_directory.chmod(0o750)
        os.chown(conf_directory, 0, pwd.getpwnam(role).pw_gid)
        installed_lock = Path('/opt/music-cluster/spark/connectors.lock.json')
        reviewed_lock = release / 'deployment/aws/connectors.lock.json'
        if installed_lock.is_symlink() or installed_lock.read_bytes() != reviewed_lock.read_bytes():
            raise RuntimeError('installed_connector_lock_differs_from_review')
        installed_lock.chmod(0o644)
        defaults = (HERE / 'spark-defaults.conf').read_text().replace('@DRIVER_PYTHON@', py)
        write(spark_conf + '/spark-defaults.conf', defaults, 0o640, role)
        write('/etc/music-cluster/control/kafka-options.json', (HERE / 'kafka-options.json').read_text(), 0o640, role)
        shutil.copyfile('/etc/music-cluster/control/tls/ca.crt', '/opt/music-cluster/spark/conf/kafka-ca.pem')
        Path('/opt/music-cluster/spark/conf/kafka-ca.pem').chmod(0o644)
    current = base / 'current'
    if current.exists() and not current.is_symlink(): raise RuntimeError('unmanaged_current_release_preserved')
    link = base / '.current-new'
    if link.is_symlink(): link.unlink()
    link.symlink_to(release, target_is_directory=True)
    link.replace(current)
    # Initial setup is explicit and idempotent; no approved catalog is invented.
    if role == 'control':
        if plan['writer_active'] and not args.skip_initialize:
            execute([py, 'backend/manage.py', 'prepare_runtime', '--apply', '--streams'], env=env, user=role, cwd=release)
            execute([py, '-m', 'pipeline.weather.prepare_store', '--apply'], env=env, user=role, cwd=release)
        unit('music-app-common', role, release, str(venv / 'bin/uvicorn') + ' backend.cafe.asgi:application --host 127.0.0.1 --port 8001 --workers 2 --proxy-headers --forwarded-allow-ips 127.0.0.1')
        commands = {
            'music-app-recommendations': py + ' backend/manage.py run_recommendations',
            'music-app-feedback-relay': py + ' backend/manage.py relay_feedback --watch',
            'music-app-feedback-consumer': py + ' -m pipeline.feedback.process',
            'music-app-weather-collector': py + ' -m pipeline.weather.run_collector',
            'music-app-weather-driver': py + ' -m pipeline.weather.submit_spark',
        }
        for name, command in commands.items(): unit(name, role, release, command)
        write('/etc/nginx/sites-available/music-app', (HERE / 'nginx.conf').read_text(), 0o600)
        default = Path('/etc/nginx/sites-enabled/default')
        if default.is_symlink(): default.unlink()
        enabled = Path('/etc/nginx/sites-enabled/music-app')
        if not enabled.exists(): enabled.symlink_to('/etc/nginx/sites-available/music-app')
        execute(['nginx', '-t'])
    else:
        if not args.skip_initialize:
            execute([py, 'manage.py', 'prepare_ads_runtime', '--apply'], env=env, user=role, cwd=release / 'ad-server/backend')
            execute([py, 'manage.py', 'refresh_ads_policy'], env=env, user=role, cwd=release / 'ad-server/backend')
        # gunicorn handles secure proxy headers only from the two owned gateways.
        unit('music-app-advertising', role, release / 'ad-server/backend', str(venv / 'bin/gunicorn') + ' config.wsgi:application --bind ' + plan['private_ip'] + ':8000 --workers 2 --timeout 30 --forwarded-allow-ips ' + ','.join(plan['controls']))
        unit('music-app-advertising-workers', role, release / 'ad-server/backend', py + ' manage.py run_ads_workers --watch')
    if role == 'control':
        # Bootstrap password is an initialization input, never a daemon credential.
        cleaned = '\n'.join(line for line in env_path.read_text().splitlines() if not line.startswith('BOOTSTRAP_ADMIN_')) + '\n'
        write(env_path, cleaned, 0o640, role)
    execute(['systemctl', 'daemon-reload'])
    units = ['music-app-common'] if role == 'control' else ['music-app-advertising', 'music-app-advertising-workers']
    if role == 'control' and plan['writer_active']: units += list(commands)
    if role == 'control' and not plan['writer_active']:
        for name in commands:
            execute(['systemctl', 'disable', '--now', name])
    for name in units:
        execute(['systemctl', 'enable', name])
        execute(['systemctl', 'restart', name])
    if role == 'control': execute(['systemctl', 'reload-or-restart', 'nginx'])
    if role == 'control' and plan['writer_active'] and not args.skip_initialize:
        execute([py, 'backend/manage.py', 'import_music_catalog_source', str(release / 'docs/handoff/music/spotify_dataset.csv'), '--schema', 'spotify-raw20-v1', '--expected-sha256', plan['music_sha256'], '--apply', '--allow-quarantined-rows'], env=env, user=role, cwd=release, timeout=7200)
    print(json.dumps({'node':node, 'release':plan['release'], 'started_units':units,
                      'writer_active':plan['writer_active'], 'music_requires_review':role == 'control'}))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__,
                          'reason':str(error) if isinstance(error, RuntimeError) else 'see_owner_only_install_log'}))
        raise SystemExit(1)
