#!/usr/bin/env bash
# Configures a separate canary supervisor unit, disabled and never started here.
set -Eeuo pipefail
umask 077
root=$(cd -- "$(dirname -- "$0")" && pwd)
[[ $EUID -eq 0 ]] || { echo '[FAIL] EC2 root required' >&2; exit 1; }
python3 - "$root" "${1:?Private runtime required}" <<'PREPARE_CONTROL_FENCING'
import hashlib,json,os,pwd,re,shutil,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);runtime=json.loads(Path(sys.argv[2]).read_text());cfg=runtime['fencing']
if runtime['node']['role']!='control' or cfg['workload_kind']!='isolated local canary; no business/S3 workload':
    raise ValueError('Explicit infrastructure canary config required; no business deployment')
query=cfg['query']
if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}',query):raise ValueError('Invalid query namespace')
service='music-control-fence-'+query+'.service'
if subprocess.run(['systemctl','is-active','--quiet',service]).returncode==0:
    raise ValueError('Active coordinator upgrade requires an explicit stop/fencing plan')
user=pwd.getpwnam('control');python=Path('/opt/music-cluster/python/bin/python3.14')
if not python.is_file():raise ValueError('Verified Python/Control host is required')
version=subprocess.run([cfg['aws_cli'],'--version'],capture_output=True,text=True,check=True,timeout=10).stdout
if not version.startswith('aws-cli/'+cfg['aws_cli_version']+' '):raise ValueError('Install exact reviewed AWS CLI v2 before this stage')
marker=Path('/var/lib/music-cluster/.aws-volume-identity.json')
if marker.is_symlink() or json.loads(marker.read_text())!={**runtime['aws'],'node':runtime['node']['name']}:
    raise ValueError('Mounted generation marker differs')
# The marker contains identity metadata only. Grant this service read access,
# retaining root ownership and preventing the Control user from changing it.
os.chown(marker,0,user.pw_gid);marker.chmod(0o640)
lock=root/'control-fencing.lock.json';lock_sha=hashlib.sha256(lock.read_bytes()).hexdigest()
if lock_sha!=cfg['dependency_lock_sha256']:raise ValueError('Private runtime/dependency lock differs')
manifest=json.loads(lock.read_text());expected={x['filename'] for x in manifest['packages']}
if {p.name for p in (root/'wheels').iterdir()}!=expected:raise ValueError('Incomplete/extra runtime wheels')
for package in manifest['packages']:
    path=root/'wheels'/package['filename']
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=package['sha256']:raise ValueError('Runtime wheel hash differs')
source=cfg['source_sha256']
if not re.fullmatch(r'[0-9a-f]{64}',source):raise ValueError('Reviewed source identity required')
home=Path('/opt/music-cluster/control-fencing')/source
venv=Path('/var/lib/music-cluster/control/fencing-venv')/lock_sha
config=Path('/etc/music-cluster/control/fencing')
for folder in (config,config/'tls',venv.parent,home.parent):
    folder.mkdir(parents=True,exist_ok=True,mode=0o750);os.chown(folder,0,user.pw_gid);folder.chmod(0o750)
def publish(path,data,mode,uid=0,gid=user.pw_gid):
    if path.is_symlink():raise ValueError('Symlink destination is not supported')
    if path.exists():
        if path.read_bytes()!=data:raise ValueError('Existing configuration differs; explicit upgrade required')
        return
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    os.chown(path.parent,0,user.pw_gid);path.parent.chmod(0o750)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    with os.fdopen(fd,'wb') as stream:stream.write(data)
    os.chown(path,uid,gid);path.chmod(mode)
for name in ('ca.crt','node.crt','node.key'):publish(config/'tls'/name,(root/'pki'/name).read_bytes(),0o640)
os.chown(config,0,user.pw_gid);os.chown(config/'tls',0,user.pw_gid)
if not venv.exists():
    temporary=venv.with_name('.'+lock_sha+'.building')
    if temporary.exists():raise ValueError('Partial dependency install retained; review before retry')
    subprocess.run([str(python),'-m','venv',str(temporary)],check=True)
    requirements=temporary/'requirements.txt'
    requirements.write_text(''.join(p['name']+'=='+p['version']+' --hash=sha256:'+p['sha256']+'\n' for p in manifest['packages']))
    # Structured argv, no index, no build or online resolver on the guest.
    subprocess.run([str(temporary/'bin/python'),'-m','pip','install','--no-index','--no-deps','--require-hashes',
        '--find-links',str(root/'wheels'),'-r',str(requirements)],check=True,stdout=subprocess.DEVNULL)
    (temporary/'reviewed-lock.json').write_bytes(lock.read_bytes());temporary.rename(venv)
if (venv/'reviewed-lock.json').read_bytes()!=lock.read_bytes():raise ValueError('Installed dependency identity differs')
for path in (venv,*venv.rglob('*')):
    if path.is_symlink():os.lchown(path,0,user.pw_gid);continue
    mode=0o750 if path.is_dir() or path.stat().st_mode & 0o100 else 0o640
    os.chown(path,0,user.pw_gid);path.chmod(mode)
for name in ('control-runner.py','control-canary.py','aws-identity.py'):publish(home/name,(root/name).read_bytes(),0o644)
for path in (root/'fencing').glob('*.py'):publish(home/'fencing'/path.name,path.read_bytes(),0o644)
publish(config/(query+'.json'),Path(sys.argv[2]).read_bytes(),0o600,user.pw_uid,user.pw_gid)
unit=('[Unit]\nDescription=Explicit Control fencing canary\nAfter=network-online.target\nWants=network-online.target\n'
      '[Service]\nType=simple\nUser=control\nGroup=control\nUMask=0077\nWorkingDirectory=/var/lib/music-cluster/control\n'
      'ExecStart='+str(venv/'bin/python')+' '+str(home/'control-runner.py')+' --runtime '+str(config/(query+'.json'))+' supervise --execute\n'
      'Restart=no\nKillMode=control-group\nKillSignal=SIGTERM\nTimeoutStopSec=180\nSendSIGKILL=yes\n'
      'NoNewPrivileges=true\nPrivateTmp=true\nProtectHome=true\nProtectSystem=strict\nReadWritePaths=/var/lib/music-cluster/control\n'
      '[Install]\nWantedBy=multi-user.target\n')
publish(Path('/etc/systemd/system')/service,unit.encode(),0o644)
subprocess.run(['systemctl','daemon-reload'],check=True)
enabled=subprocess.run(['systemctl','is-enabled',service],capture_output=True,text=True)
if enabled.returncode==0:raise ValueError('Coordinator unit must remain disabled; inspect operator activation')
print('[PASS] Isolated canary supervisor installed; unit disabled and not started. Bootstrap/activation require explicit execution.')
PREPARE_CONTROL_FENCING
