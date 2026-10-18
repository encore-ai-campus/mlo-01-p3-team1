#!/usr/bin/env python3
"""Explicit weather DB add-on. Never reset data, rotate users, or replace app env."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

SHELL_VERSION = '2.13.0'
SHELL_SHA = '63b71930a7065acd199fe68babba6dda2c045aa1786f6091089c595773638119'
SHELL_URL = 'https://downloads.mongodb.com/compass/mongodb-mongosh_2.13.0_amd64.deb'
SHELL_HOME = Path('/opt/music-cluster/mongodb-clients/mongosh') / SHELL_VERSION
ENV_FILE = Path('/etc/music-cluster/control/weather-database.env')


def validate(c, runtime):
    if c['aws'] != runtime['aws'] or c['node'] != runtime['node']['name']:
        raise ValueError('Weather payload installation identity mismatch')
    if runtime['node']['role'] not in ('control', 'mongodb') or runtime['env']['ENVIRONMENT'] != 'aws':
        raise ValueError('Only the provisioned MongoDB and Control hosts are allowed')
    for key in ('project', 'environment', 'generation'):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}', c['aws'][key]):
            raise ValueError('Invalid AWS namespace')
    d = c['database']
    if (d['database'], d['username'], d['auth_source'], d['port']) != ('weather', 'weather_app', 'weather', 27017):
        raise ValueError('Only the dedicated weather database/user/port is supported')
    import ipaddress
    address = ipaddress.ip_address(d['host'])
    if address.version != 4 or not any(address in ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('Provisioned private MongoDB address required')
    if not re.fullmatch(r'[A-Za-z0-9_-]{64}', c['password']):
        raise ValueError('A private, preserved generation credential is required')


def environment(c):
    d = c['database']
    values = {'WEATHER_MONGO_HOST': d['host'], 'WEATHER_MONGO_PORT': d['port'],
              'WEATHER_MONGO_DATABASE': d['database'], 'WEATHER_MONGO_USER': d['username'],
              'WEATHER_MONGO_PASSWORD': c['password'], 'WEATHER_MONGO_AUTH_SOURCE': d['auth_source'],
              'WEATHER_MONGO_TLS': 'true', 'WEATHER_MONGO_TLS_CA_FILE': '/etc/music-cluster/control/tls/ca.crt'}
    return ''.join(k + '=' + str(v) + '\n' for k, v in values.items())


def write_once(path, content, *, uid=0, gid=0, mode=0o600):
    """An explicit retry can verify identical bytes; drift is never overwritten."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing a symlink configuration')
    if path.exists():
        if path.read_text() != content or path.stat().st_uid != uid or path.stat().st_gid != gid or path.stat().st_mode & 0o777 != mode:
            raise ValueError('Existing weather configuration differs; no overwrite or rotation')
        return False
    fd, temporary = tempfile.mkstemp(prefix='.weather-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            os.fchmod(handle.fileno(), mode);os.fchown(handle.fileno(), uid, gid)
            handle.write(content);handle.flush();os.fsync(handle.fileno())
        # Hard-link publishes without overwriting an intervening creation.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def command(args, **kw):
    result = subprocess.run(args, capture_output=True, text=True, timeout=180, **kw)
    if result.returncode:
        folder = Path('/var/lib/music-cluster/weather-mongodb-diagnostics')
        folder.mkdir(mode=0o700, exist_ok=True);folder.chmod(0o700)
        path = folder / 'last-command-error.json'
        path.write_text(json.dumps({'stdout': result.stdout, 'stderr': result.stderr, 'returncode': result.returncode}))
        path.chmod(0o600)
        raise ValueError('Weather MongoDB command failed; private diagnostic output retained by caller')
    return result.stdout


def install_client():
    target = SHELL_HOME
    for parent in (target.parent.parent, target.parent):
        if parent.is_symlink():
            raise ValueError('Client parent must not be a symlink')
        if not parent.exists():
            parent.mkdir(mode=0o755);parent.chmod(0o755)
    if target.exists() or target.is_symlink():
        if target.is_symlink():raise ValueError('Client target is a symlink')
        marker = json.loads((target / 'verified.json').read_text())
        if marker['deb_sha256'] != SHELL_SHA:
            raise ValueError('Installed client package differs from lock')
        for relative, digest in marker['files'].items():
            p = target / relative
            if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                raise ValueError('Installed client bytes changed')
        return str(target / 'usr/bin/mongosh')
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='.mongosh-') as work:
        work = Path(work);archive = work / 'client.deb';digest = hashlib.sha256();size = 0
        with urlopen(SHELL_URL, timeout=30) as response, archive.open('wb') as handle:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 256 * 1024 * 1024:raise ValueError('Client package exceeds the reviewed bound')
                digest.update(chunk);handle.write(chunk)
        if digest.hexdigest() != SHELL_SHA:raise ValueError('Client package checksum differs from lock')
        stage = work / 'extract';stage.mkdir(mode=0o755)
        command(['dpkg-deb', '--extract', str(archive), str(stage)])
        files = {}
        for p in stage.rglob('*'):
            if p.is_symlink():
                if not p.resolve().is_relative_to(stage.resolve()):raise ValueError('Client archive symlink escapes installation')
            elif p.is_file():files[p.relative_to(stage).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
        binary = stage / 'usr/bin/mongosh'
        if binary.is_symlink() or not binary.is_file() or command([str(binary), '--version']).strip() != SHELL_VERSION:
            raise ValueError('Extracted MongoDB client version mismatch')
        (stage / 'verified.json').write_text(json.dumps({'deb_sha256': SHELL_SHA, 'version': SHELL_VERSION, 'files': files}))
        (stage / 'verified.json').chmod(0o644);stage.chmod(0o755)
        stage.rename(target)
    return str(target / 'usr/bin/mongosh')


def shell(script, host, port, ca, *, binary='mongosh', user=None, folder=None):
    with tempfile.TemporaryDirectory(dir=folder, prefix='command-') as work:
        work = Path(work);path = work / 'command.js';path.write_text(script);path.chmod(0o600)
        if user:
            account = pwd.getpwnam(user);os.chown(work, account.pw_uid, account.pw_gid);os.chown(path, account.pw_uid, account.pw_gid)
        args = [binary, '--quiet', '--norc', '--host', host, '--port', str(port), '--tls', '--tlsCAFile', ca, '--file', str(path)]
        if user:args = ['runuser', '-u', user, '--', *args]
        text = command(args)
        # Shell diagnostics are not copied into SSM output.
        return json.loads(text.strip().splitlines()[-1])


def provision(c, runtime, payload_path, runtime_path):
    if runtime['node']['role'] != 'mongodb':raise ValueError('MongoDB node required')
    script = 'const fs=require("fs");const c=JSON.parse(fs.readFileSync(' + json.dumps(str(payload_path)) + ',"utf8"));const r=JSON.parse(fs.readFileSync(' + json.dumps(str(runtime_path)) + ',"utf8"));\n' + r'''
const a=db.getSiblingDB('admin');const authenticated=a.auth(r.database.admin_user,r.env.MONGO_ADMIN_PASSWORD);
if(!(authenticated===1||authenticated.ok===1))throw Error('Admin authentication failed');
const t=db.getSiblingDB('weather');const expected={...c.aws,purpose:'weather-control-driver'};
let u=t.getUser('weather_app');let created=false;
if(u===null){t.createUser({user:'weather_app',pwd:c.password,roles:[{role:'readWrite',db:'weather'}],mechanisms:['SCRAM-SHA-256'],customData:expected});created=true;u=t.getUser('weather_app');}
if(u.roles.length!==1||u.roles[0].role!=='readWrite'||u.roles[0].db!=='weather'||u.mechanisms.length!==1||u.mechanisms[0]!=='SCRAM-SHA-256')throw Error('Existing weather privileges differ');
if(Object.keys(u.customData||{}).length!==Object.keys(expected).length||Object.keys(expected).some(k=>u.customData[k]!==expected[k]))throw Error('Existing weather namespace differs');
print(JSON.stringify({created:created,database:'weather',user:'weather_app',roles:[{role:'readWrite',db:'weather'}],mechanisms:['SCRAM-SHA-256'],user_id:String(u.userId),credential_rotated:false,data_reset:false}));
'''
    return shell(script, '127.0.0.1', 27017, '/etc/music-cluster/mongodb/tls/ca.crt')


def probe_script(test_id, phase):
    if not re.fullmatch(r'[0-9a-f]{16}', test_id) or phase not in ('first', 'second', 'retry'):
        raise ValueError('Explicit bounded probe ID and phase required')
    script = 'const fs=require("fs");const e=Object.fromEntries(fs.readFileSync(' + json.dumps(str(ENV_FILE)) + r''',"utf8").trim().split("\n").map(l=>{const i=l.indexOf("=");return [l.slice(0,i),l.slice(i+1)];}));''' + '\n'
    script += 'const phase=' + json.dumps(phase) + ';const id=' + json.dumps(test_id) + ';\n' + r'''
const t=db.getSiblingDB(e.WEATHER_MONGO_AUTH_SOURCE);const ok=t.auth(e.WEATHER_MONGO_USER,e.WEATHER_MONGO_PASSWORD);
if(!(ok===1||ok.ok===1))throw Error('Weather authentication failed');
const collection='infra_smoke_'+id;const present=t.getCollectionInfos({name:collection}).length>0;
if(phase==='first'&&present)throw Error('Existing probe collection cannot be reset or replayed');
if(phase!=='first'&&!present)throw Error('Existing first phase required');
const col=t.getCollection(collection);const start=phase==='second'?9:0;const end=phase==='first'?9:18;
for(let i=start;i<end;i++){const result=col.replaceOne({_id:'row-'+i},{_id:'row-'+i,id:i,score:i*10},{upsert:true});if(!result.acknowledged)throw Error('Write unacknowledged');}
const rows=col.find({}).toArray();const expected=phase==='first'?9:18;
if(rows.length!==expected||new Set(rows.map(r=>r.id)).size!==expected||rows.some(r=>r._id!=='row-'+r.id||r.score!==r.id*10||r.id<0||r.id>=expected))throw Error('Probe rows mismatch');
let denied=0;
for(const d of ['advertising','admin']){try{db.getSiblingDB(d).getCollection('infra_weather_denied').findOne({_id:id});throw Error('Unexpected cross-database access');}catch(error){if(error.code!==13)throw error;denied++;}}
const auth=db.getSiblingDB('admin').runCommand({connectionStatus:1}).authInfo;
if(auth.authenticatedUserRoles.length!==1||auth.authenticatedUserRoles[0].role!=='readWrite'||auth.authenticatedUserRoles[0].db!=='weather')throw Error('Unexpected authenticated roles');
print(JSON.stringify({phase:phase,rows:rows.length,duplicate_or_missing_rows:0,cross_database_denials:denied,auth_source:'weather',tls_hostname_verification:true,service_user:'control',data_reset:false,collection_preserved:true}));
'''
    return script


def probe(c, test_id, phase):
    script = probe_script(test_id, phase)
    folder = Path('/var/lib/music-cluster/weather-mongodb-tests')
    account = pwd.getpwnam('control')
    if not folder.exists():folder.mkdir(mode=0o700);os.chown(folder, account.pw_uid, account.pw_gid)
    return shell(script, c['database']['host'], 27017, '/etc/music-cluster/control/tls/ca.crt',
                 binary=str(SHELL_HOME / 'usr/bin/mongosh'), user='control', folder=folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True);parser.add_argument('--payload', required=True)
    parser.add_argument('--stage', choices=('provision', 'environment', 'client', 'probe'), required=True)
    parser.add_argument('--test-id');parser.add_argument('--phase');parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:print('Preparation only; no host/database mutation');return
    runtime_path = Path(args.runtime);runtime = json.loads(runtime_path.read_text());payload_path = Path(args.payload);c = json.loads(payload_path.read_text());validate(c, runtime)
    if os.geteuid() != 0 or platform.system() != 'Linux' or platform.machine() != 'x86_64':raise ValueError('Ubuntu EC2 root required')
    for name in ('aws-identity', 'init-disk'):
        spec = importlib.util.spec_from_file_location(name, runtime_path.parent / (name + '.py'))
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.verify(runtime, module.identity) if name == 'aws-identity' else module.initialize(runtime, check_only=True)
    if args.stage == 'provision':report = provision(c, runtime, payload_path, runtime_path)
    else:
        if runtime['node']['role'] != 'control':raise ValueError('Control host required')
        if args.stage == 'environment':
            group = pwd.getpwnam('control').pw_gid
            report = {'created': write_once(ENV_FILE, environment(c), gid=group, mode=0o640), 'private_environment': True, 'advertising_or_postgres_environment_replaced': False}
        elif args.stage == 'client':report = {'client': 'mongosh', 'version': SHELL_VERSION, 'binary': install_client(), 'global_package_or_app_venv_changed': False}
        else:report = probe(c, args.test_id, args.phase)
    print(json.dumps(report))


if __name__ == '__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'failed': True, 'error_type': type(error).__name__, 'no_automatic_retry_reset_or_rotation': True}));raise SystemExit(1)
