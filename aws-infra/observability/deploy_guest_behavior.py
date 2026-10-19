"""Explicit, isolated guest analytics setup. Private inputs; no infrastructure creation."""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone

os.umask(0o077)
HERE = Path(__file__).resolve().parent
CONF = Path('/etc/music-cluster/guest-analytics')
DATA = Path('/var/lib/music-cluster/guest-analytics')


def write(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.new')
    temp.write_text(value)
    temp.chmod(mode)
    temp.replace(path)


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError('subprocess_failed:' + Path(args[0]).name)
    return result.stdout


def postgres(c):
    role = 'music_guest_analytics'
    columns = {
        'common_feedbackevent': 'event_id,event_type,occurred_at,source_playlist_id,track_id,payload,is_test',
        'common_feedbackstate': 'id,target_kind,value,last_event_id,playlist_id,track_id',
        'common_outbox': 'event_id,state', 'common_projection': 'event_id',
        'recommendation_family': 'id,excluded', 'recommendation_playlist': 'id,job_id',
        'recommendation_job': 'id,catalog_id,family_id,method', 'recommendation_catalog': 'version,is_test'}
    def psql(sql):
        return run(['sudo', '-u', 'postgres', '/usr/lib/postgresql/16/bin/psql', '-X',
                    '-v', 'ON_ERROR_STOP=1', '-h', '/run/music-postgresql', '-d', 'music', '-At'], input=sql)
    state = Path('/var/lib/music-cluster/postgresql/guest-analytics-owner.json')
    exists = psql("SELECT count(*) FROM pg_roles WHERE rolname='music_guest_analytics';").strip() == '1'
    fingerprint = hashlib.sha256(c['pg_password'].encode()).hexdigest()
    if exists and (not state.exists() or json.loads(state.read_text())['credential_sha256'] != fingerprint):
        raise RuntimeError('existing_postgres_role_not_owned')
    if not exists:
        salt = secrets.token_bytes(16)
        key = hashlib.pbkdf2_hmac('sha256', c['pg_password'].encode(), salt, 4096)
        client_key = hmac.new(key, b'Client Key', hashlib.sha256).digest()
        stored = hashlib.sha256(client_key).digest()
        server = hmac.new(key, b'Server Key', hashlib.sha256).digest()
        b64 = lambda b: base64.b64encode(b).decode()
        verifier = 'SCRAM-SHA-256$4096:' + b64(salt) + '$' + b64(stored) + ':' + b64(server)
        sql = "BEGIN; CREATE ROLE music_guest_analytics LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 2 PASSWORD '" + verifier + "';\n"
        sql += "ALTER ROLE music_guest_analytics SET default_transaction_read_only=on; ALTER ROLE music_guest_analytics SET statement_timeout='5s'; ALTER ROLE music_guest_analytics SET idle_in_transaction_session_timeout='30s'; GRANT CONNECT ON DATABASE music TO music_guest_analytics; GRANT USAGE ON SCHEMA public TO music_guest_analytics;\n"
        for table, names in columns.items():
            sql += 'GRANT SELECT (' + names + ') ON ' + table + ' TO music_guest_analytics;\n'
        psql(sql + 'COMMIT;')
        write(state, json.dumps({'credential_sha256': fingerprint, 'managed': 'music-guest-v1'}))
    hba = Path('/etc/music-cluster/postgresql/pg_hba.conf')
    old = hba.read_text()
    line = 'hostssl music ' + role + ' ' + c['collector_ip'] + '/32 scram-sha-256'
    if line not in old.splitlines():
        if role in old: raise RuntimeError('unexpected_existing_guest_hba')
        backup = hba.with_name('pg_hba.before-guest-analytics.conf')
        if not backup.exists(): write(backup, old)
        write(hba, old.replace('host all all 0.0.0.0/0 reject', line + '\nhost all all 0.0.0.0/0 reject'))
        shutil.chown(hba, user='postgres', group='postgres')
        assert psql('SELECT pg_reload_conf();').strip() == 't'
    assert psql('SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;').strip() == '0'
    print(json.dumps({'postgres_role': role, 'column_select_only': True, 'tls_collector_only': True}))


def elastic(c):
    from guest_behavior_export import Elasticsearch
    from guest_behavior_elastic_plan import plans
    client = Elasticsearch(c, admin=True)
    ledger_path = Path('/var/lib/music-cluster/observability/guest-elastic-owned.json')
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    operations = plans()
    def existing(path):
        try: return client.request('GET', path)
        except RuntimeError as e:
            if str(e) == 'elasticsearch_http_404': return None
            raise
    # No arbitrary replacement of resources created by another operator.
    for item in operations:
        before = existing(item['path'])
        if before and item['path'] not in ledger:
            raise RuntimeError('guest_elastic_resource_not_owned:' + item['path'])
    for item in operations:
        client.request(item['method'], item['path'], item['body'])
        ledger[item['path']] = True
        write(ledger_path, json.dumps(ledger))
    username = c['elasticsearch']['writer_user']
    if existing('/_security/user/' + username) and not ledger.get('writer'):
        raise RuntimeError('guest_writer_not_owned')
    client.request('PUT', '/_security/user/' + username,
                   {'password': c['elasticsearch']['writer_password'], 'roles': ['analytics_mlo_guest_writer']})
    ledger['writer'] = True; write(ledger_path, json.dumps(ledger))
    user = client.request('GET', '/_security/user/ops_admin')['ops_admin']
    if 'analytics_mlo_guest_viewer' not in user['roles']:
        if 'viewer_roles_before' not in ledger:
            ledger['viewer_roles_before'] = user['roles']; write(ledger_path, json.dumps(ledger))
        client.request('PUT', '/_security/user/ops_admin', {'roles': [*user['roles'], 'analytics_mlo_guest_viewer']})
    for name in ['analytics-mlo-guest-events-' + datetime.now(timezone.utc).strftime('%Y.%m'), 'analytics-mlo-guest-summary-v1']:
        if existing('/' + name) is None: client.request('PUT', '/' + name, {})
    print(json.dumps({'templates': 2, 'dedicated_writer': True, 'existing_viewer_roles_preserved': True}))


def collector(c):
    native = json.loads(Path('/etc/music-cluster/runtime.json').read_text())
    assert native['node']['name'] == 'control-a', 'single_collector_control_a_required'
    unit = Path('/etc/systemd/system/music-app-common.service').read_text()
    exe = re.search(r'^ExecStart=([^ ]+)', unit, re.M).group(1)
    python = str(Path(exe).with_name('python'))
    env = {}
    for line in Path('/etc/music-cluster/control/application.env').read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and not key.startswith('#'): env[key] = value
    assert env.get('PGSSLMODE') == 'verify-full'
    if subprocess.run(['id', 'music-guest-analytics'], capture_output=True).returncode:
        run(['useradd', '--system', '--home-dir', str(DATA), '--shell', '/usr/sbin/nologin', 'music-guest-analytics'])
    import pwd
    identity = pwd.getpwnam('music-guest-analytics')
    DATA.mkdir(exist_ok=True); DATA.chmod(0o700); shutil.chown(DATA, user=identity.pw_uid, group=identity.pw_gid)
    CONF.mkdir(exist_ok=True); CONF.chmod(0o750); shutil.chown(CONF, user='root', group=identity.pw_gid)
    destination = Path('/opt/music-observability/guest-v1')
    destination.mkdir(parents=True, exist_ok=True); destination.chmod(0o755)
    for name in ['guest_behavior_export.py', 'guest_behavior_runner.py']:
        write(destination / name, (HERE / name).read_text(), 0o644)
    conf = {'application_root': '/opt/music-apps/control/current',
            'database': {'ENGINE': 'django.db.backends.postgresql', 'NAME': env['PGDATABASE'],
                         'USER': 'music_guest_analytics', 'PASSWORD': c['pg_password'],
                         'HOST': env['PGHOST'], 'PORT': env['PGPORT'],
                         'OPTIONS': {'sslmode': 'verify-full', 'sslrootcert': str(CONF / 'ca.crt'), 'connect_timeout': 5}},
            'elasticsearch': {k: v for k, v in c['elasticsearch'].items() if not k.startswith('admin_')},
            'cursor_path': str(DATA / 'cursor.json'), 'batch_size': 500, 'initial_lookback_days': 30}
    conf['elasticsearch']['ca_file'] = str(CONF / 'ca.crt')
    shutil.copyfile(env['PGSSLROOTCERT'], CONF / 'ca.crt'); (CONF / 'ca.crt').chmod(0o644)
    config = CONF / 'runtime.json'; write(config, json.dumps(conf), 0o640); shutil.chown(config, user='root', group=identity.pw_gid)
    # The service gets only dedicated read-only PG and isolated ES credentials.
    write('/etc/systemd/system/music-guest-analytics.service', '''[Unit]
Description=Anonymous music feedback analytics (read-only PostgreSQL)
After=network-online.target
[Service]
Type=oneshot
User=music-guest-analytics
Group=music-guest-analytics
WorkingDirectory=/opt/music-observability/guest-v1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=''' + python + ' ' + str(destination / 'guest_behavior_runner.py') + ' --config ' + str(config) + '''
TimeoutStartSec=180
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/music-cluster/guest-analytics
MemoryMax=256M
CPUQuota=25%
''', 0o644)
    write('/etc/systemd/system/music-guest-analytics.timer', '''[Unit]
Description=Refresh guest behavior analytics every minute
[Timer]
OnBootSec=45s
OnUnitInactiveSec=60s
AccuracySec=5s
Persistent=true
Unit=music-guest-analytics.service
[Install]
WantedBy=timers.target
''', 0o644)
    run(['systemctl', 'daemon-reload'])
    access = run(['runuser', '-u', 'music-guest-analytics', '--', python, str(destination / 'guest_behavior_runner.py'), '--config', str(config), '--verify-access'])
    print(access.strip())
    dry = run(['runuser', '-u', 'music-guest-analytics', '--', python, str(destination / 'guest_behavior_runner.py'), '--config', str(config), '--dry-run'])
    print(dry.strip())
    run(['systemctl', 'start', 'music-guest-analytics.service'])
    run(['systemctl', 'enable', '--now', 'music-guest-analytics.timer'])
    print(json.dumps({'collector': 'control-a', 'timer': 'enabled', 'dedicated_os_user': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['postgres', 'elastic', 'collector'])
    parser.add_argument('config')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    if args.action == 'postgres':
        native = json.loads((Path('/var/lib/music-cluster/aws-state') / config['generation'] / 'postgresql-identity.json').read_text())
        native = {'node': {'name': native['node']}}
    else:
        native = json.loads(Path('/etc/music-cluster/runtime.json').read_text())
    expected = {'postgres': 'postgresql', 'elastic': 'control-b', 'collector': 'control-a'}[args.action]
    assert native['node']['name'] == expected
    import fcntl
    with Path('/run/music-guest-analytics-install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        globals()[args.action](config)
