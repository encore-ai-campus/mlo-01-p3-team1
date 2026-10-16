#!/usr/bin/env python3
"""Ubuntu EC2-only DB install/health. Do not invoke on a workstation or local VM."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import pwd
import shutil
import subprocess
import time
import tempfile
from urllib.request import urlopen

from database_config import validate, postgres_files, mongo_config, unit

BASE = Path('/var/lib/music-cluster')
CONF = Path('/etc/music-cluster')
ROOT = Path(__file__).resolve().parent


def run(*args, input=None, env=None, cwd=None, check=True):
    # Captured output may contain database errors. Never forward it to SSM stdout.
    result = subprocess.run(args, input=input, env=env, cwd=cwd, capture_output=True, text=True, timeout=1800)
    if check and result.returncode:
        raise ValueError('Database operation failed: ' + Path(args[0]).name)
    return result


def save(path, data, user=None, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(data)
    temporary.chmod(mode)
    if user:
        account = pwd.getpwnam(user)
        os.chown(temporary, account.pw_uid, account.pw_gid)
    temporary.replace(path)


def guard(c):
    validate(c)
    if platform.system() != 'Linux' or os.geteuid() != 0 or platform.machine() != 'x86_64':
        raise ValueError('Ubuntu EC2 amd64/root required')
    os_release = Path('/etc/os-release').read_text()
    if 'ID=ubuntu\n' not in os_release or 'VERSION_ID="24.04"' not in os_release:
        raise ValueError('Ubuntu 24.04 required')
    # These checks precede package/config/service mutations, even for direct invocation.
    for name in ('aws-identity', 'init-disk'):
        spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if name == 'aws-identity':
            module.verify(c, module.identity)
        else:
            module.initialize(c, check_only=True)


def install_packages(c):
    kind = c['node']['role']
    lock = c['database_versions'][kind]
    cache = Path('/var/cache/music-cluster/database')
    cache.mkdir(parents=True, exist_ok=True)
    run('systemctl', 'mask', 'mongod.service' if kind == 'mongodb' else 'postgresql.service')
    env = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}
    if kind == 'postgresql':
        # Prevent postinst from creating an unmanaged root-volume main cluster.
        save('/etc/postgresql-common/createcluster.conf', 'create_main_cluster = false\n', mode=0o644)
    else:
        run('apt-get', 'update', env=env)
        run('apt-get', '-o', 'DPkg::Lock::Timeout=120', 'install', '-y', '--no-install-recommends', 'gnupg', 'ca-certificates', env=env)
        key = urlopen(lock['signing_key_url'], timeout=30).read()
        if hashlib.sha256(key).hexdigest() != lock['signing_key_sha256']:
            raise ValueError('MongoDB signing-key checksum mismatch')
        armored = cache / 'mongodb.asc'
        armored.write_bytes(key)
        run('gpg', '--batch', '--yes', '--dearmor', '--output', '/usr/share/keyrings/music-mongodb-8.0.gpg', str(armored))
        save('/etc/apt/sources.list.d/music-mongodb-8.0.list',
             'deb [arch=amd64 signed-by=/usr/share/keyrings/music-mongodb-8.0.gpg] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse\n', mode=0o644)
    run('apt-get', 'update', env=env)
    files = []
    for package in lock['packages']:
        path = cache / package['filename']
        if not path.exists():
            run('apt-get', 'download', package['name'] + '=' + package['version'], cwd=cache, env=env)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != package['sha256']:
            raise ValueError('Database package checksum mismatch')
        files.append(str(path))
    run('apt-get', '-o', 'DPkg::Lock::Timeout=120', 'install', '-y', '--no-install-recommends', *files, env=env)
    for package in lock['packages']:
        actual = run('dpkg-query', '-W', '-f=${Version}', package['name']).stdout.strip()
        if actual != package['version']:
            raise ValueError('Installed database version differs from lock')
    run('apt-mark', 'hold', *[p['name'] for p in lock['packages']])


def tls(c):
    kind = c['node']['role']
    user = 'postgres' if kind == 'postgresql' else 'mongodb'
    target = CONF / kind / 'tls'
    run('install', '-d', '-o', user, '-g', user, '-m', '0750', str(CONF / kind), str(target), str(BASE / kind))
    source = ROOT / 'core/pki'
    for name in ('ca.crt', 'node.crt', 'node.key'):
        if not (source / name).is_file():
            raise ValueError('Database TLS material missing')
        run('openssl', 'x509', '-in', str(source / 'node.crt'), '-checkend', '604800', '-noout')
        save(target / name, (source / name).read_text(), user)
    if kind == 'mongodb':
        save(target / 'server.pem', (source / 'node.key').read_text() + (source / 'node.crt').read_text(), user)


def wait_healthy(c):
    for attempt in range(30):
        try:
            health(c)
            return
        except ValueError:
            if attempt == 29:
                raise
            time.sleep(2)


def postgres(c):
    d = c['database']
    folder = BASE / 'postgresql/data'
    if not (folder / 'PG_VERSION').exists():
        if folder.exists() and any(folder.iterdir()):
            raise ValueError('Partial PostgreSQL data directory; never delete/reinitialize automatically')
        run('install', '-d', '-o', 'postgres', '-g', 'postgres', '-m', '0700', str(folder))
        run('runuser', '-u', 'postgres', '--', '/usr/lib/postgresql/16/bin/initdb', '-D', str(folder),
            '--auth-local=peer', '--auth-host=scram-sha-256', '--encoding=UTF8')
    if (folder / 'PG_VERSION').read_text().strip() != '16':
        raise ValueError('PostgreSQL data version differs; no automatic upgrade/reset')
    for name, data in postgres_files(c).items():
        save(CONF / 'postgresql' / name, data, 'postgres')
    save('/etc/systemd/system/music-postgresql.service', unit('postgresql'), mode=0o644)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'music-postgresql.service')
    psql = ['runuser', '-u', 'postgres', '--', '/usr/lib/postgresql/16/bin/psql', '-X', '-v', 'ON_ERROR_STOP=1',
            '-h', '/run/music-postgresql', '-p', str(d['port']), '-d', 'postgres', '-At']
    for attempt in range(30):
        if run(*psql, input='SELECT 1;', check=False).returncode == 0:
            break
        time.sleep(2)
    else:
        raise ValueError('PostgreSQL startup did not finish')
    if run(*psql, input=f"SELECT 1 FROM pg_roles WHERE rolname='{d['user']}';").stdout.strip() != '1':
        run(*psql, input=f"CREATE ROLE \"{d['user']}\" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{c['env']['POSTGRES_APP_PASSWORD']}';")
    if run(*psql, input=f"SELECT 1 FROM pg_database WHERE datname='{d['database']}';").stdout.strip() != '1':
        run(*psql, input=f"CREATE DATABASE \"{d['database']}\" OWNER \"{d['user']}\";")
    wait_healthy(c)


def mongo_script(c, body, check=True):
    # Secrets are read from a root-only file by mongosh, never placed in argv/script text.
    script = "const c=JSON.parse(require('fs').readFileSync('/etc/music-cluster/mongodb/runtime.json','utf8'));\n" + body
    with tempfile.TemporaryDirectory(dir=CONF/'mongodb') as folder:
        path=Path(folder)/'command.js';path.write_text(script);path.chmod(0o600)
        return run('mongosh', '--quiet', '--norc', '--host', '127.0.0.1', '--port', str(c['database']['port']),
                   '--tls', '--tlsCAFile', str(CONF / 'mongodb/tls/ca.crt'), '--file', str(path), check=check)


def mongodb(c):
    run('install', '-d', '-o', 'mongodb', '-g', 'mongodb', '-m', '0700', str(BASE / 'mongodb/data'))
    save(CONF / 'mongodb/runtime.json', json.dumps(c))
    save(CONF / 'mongodb/mongod.conf', mongo_config(c, loopback_only=True), 'mongodb')
    save('/etc/systemd/system/music-mongodb.service', unit('mongodb'), mode=0o644)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'music-mongodb.service')
    for attempt in range(30):
        if mongo_script(c, 'if(db.runCommand({ping:1}).ok!==1) quit(1);', check=False).returncode == 0:
            break
        time.sleep(2)
    else:
        raise ValueError('MongoDB startup did not finish')
    mongo_script(c, """
const a=db.getSiblingDB('admin');
let authenticated=false;
try { const r=a.auth(c.database.admin_user,c.env.MONGO_ADMIN_PASSWORD); authenticated=r===1||r.ok===1; } catch(e) {}
if(!authenticated) {
  a.createUser({user:c.database.admin_user,pwd:c.env.MONGO_ADMIN_PASSWORD,roles:[{role:'root',db:'admin'}],mechanisms:['SCRAM-SHA-256']});
  const r=a.auth(c.database.admin_user,c.env.MONGO_ADMIN_PASSWORD); if(!(r===1||r.ok===1)) quit(2);
}
const t=db.getSiblingDB(c.database.database);
if(!t.getUser(c.database.user)) t.createUser({user:c.database.user,pwd:c.env.MONGO_APP_PASSWORD,roles:[{role:'readWrite',db:c.database.database}],mechanisms:['SCRAM-SHA-256']});
""")
    # Expose the private address only after TLS and both users are ready.
    save(CONF / 'mongodb/mongod.conf', mongo_config(c), 'mongodb')
    run('systemctl', 'restart', 'music-mongodb.service')
    wait_healthy(c)


def health(c):
    kind = c['node']['role']
    d = c['database']
    if kind == 'postgresql':
        env = {**os.environ, 'PGPASSWORD': c['env']['POSTGRES_APP_PASSWORD'], 'PGSSLMODE': 'verify-full',
               'PGSSLROOTCERT': str(CONF / 'postgresql/tls/ca.crt'), 'PGCONNECT_TIMEOUT': '5'}
        run('/usr/lib/postgresql/16/bin/psql', '-X', '-v', 'ON_ERROR_STOP=1', '-h', '127.0.0.1',
            '-p', str(d['port']), '-U', d['user'], '-d', d['database'], '-At', env=env,
            input='BEGIN; CREATE TEMP TABLE aws_health(v integer); INSERT INTO aws_health VALUES(1); SELECT v FROM aws_health; ROLLBACK;')
    else:
        mongo_script(c, """
const t=db.getSiblingDB(c.database.database);
const r=t.auth(c.database.user,c.env.MONGO_APP_PASSWORD); if(!(r===1||r.ok===1)) quit(2);
const id=new ObjectId();
try { t.getCollection('_infra_health').insertOne({_id:id}); if(!t.getCollection('_infra_health').findOne({_id:id})) quit(3); }
finally { t.getCollection('_infra_health').deleteOne({_id:id}); }
""")
    run('systemctl', 'is-active', '--quiet', 'music-' + kind + '.service')


def install(c):
    kind = validate(c)
    state = BASE / 'aws-state' / c['aws']['generation']
    identity = {**c['aws'], 'node': c['node']['name'], 'kind': kind,
                'desired_sha256': hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()}
    marker = state / (kind + '-identity.json')
    complete = state / (kind + '-installed.json')
    if marker.exists():
        if json.loads(marker.read_text()) != identity:
            raise ValueError('Database identity/secret/config changed; no automatic reset')
    else:
        if (BASE / kind).exists() and any((BASE / kind).iterdir()) or (CONF / kind).exists():
            raise ValueError('Unmanaged database files exist; refusing adoption')
        if shutil.which('mongod' if kind == 'mongodb' else 'psql'):
            raise ValueError('Unmanaged database package exists; inspect before installation')
        save(marker, json.dumps(identity))
    if complete.exists():
        health(c)
        return
    install_packages(c)
    tls(c)
    (postgres if kind == 'postgresql' else mongodb)(c)
    save(complete, json.dumps({'kind': kind, 'generation': c['aws']['generation'],
         'installed_at': datetime.now(timezone.utc).isoformat(), 'packages': c['database_versions'][kind]['packages'],
         'service_validation': 'local TLS/authenticated read-write; remote app connectivity remains separate'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime')
    parser.add_argument('stage', choices=('postgresql', 'mongodb', 'database-health', 'preflight'))
    args = parser.parse_args()
    c = json.loads(Path(args.runtime).read_text())
    guard(c)
    if args.stage == 'database-health':
        health(c)
    elif args.stage != 'preflight':
        if args.stage != c['node']['role']:
            raise ValueError('Database stage does not match the node role')
        install(c)
    print('[PASS] Native database stage completed; remote application validation remains separate')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit('[FAIL] Native database stage failed; secrets are not included in this output')
