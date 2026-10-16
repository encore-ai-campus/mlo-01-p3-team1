"""Explicit, data-preserving EC2 standalone -> single-member replica-set migration."""
import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import pwd
import secrets
import socket
import shutil
import subprocess
import tempfile
import time
from urllib.request import Request,urlopen

CONF=Path('/etc/music-cluster/mongodb')
DATA=Path('/var/lib/music-cluster/mongodb')

def run(argv,check=True):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=300)
    if check and result.returncode:raise RuntimeError('command_failed:'+Path(argv[0]).name)
    return result

def save(path,text,mode=0o600,user=None):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.new')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    with os.fdopen(fd,'w') as stream:stream.write(text)
    if user:
        account=pwd.getpwnam(user);os.chown(temporary,account.pw_uid,account.pw_gid)
    temporary.replace(path)

def mongo(body):
    prefix="const c=JSON.parse(require('fs').readFileSync('/etc/music-cluster/mongodb/runtime.json'));const a=db.getSiblingDB('admin');if(!a.auth(c.database.admin_user,c.env.MONGO_ADMIN_PASSWORD))quit(2);\n"
    with tempfile.NamedTemporaryFile(mode='w',suffix='.js',dir=CONF) as stream:
        stream.write(prefix+body);stream.flush()
        result=run(['mongosh','--quiet','--norc','--host','127.0.0.1','--tls','--tlsCAFile',str(CONF/'tls/ca.crt'),'--file',stream.name])
    return json.loads(result.stdout.strip().splitlines()[-1])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--generation',required=True);parser.add_argument('--instance-id',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if os.geteuid()!=0 or not os.path.ismount('/var/lib/music-cluster'):raise RuntimeError('mounted_EC2_database_required')
    runtime=json.loads((CONF/'runtime.json').read_text())
    if runtime['aws']['generation']!=args.generation or runtime['node']['name']!='mongodb':raise RuntimeError('generation_or_node_mismatch')
    token=urlopen(Request('http://169.254.169.254/latest/api/token',method='PUT',headers={'X-aws-ec2-metadata-token-ttl-seconds':'60'}),timeout=3).read().decode()
    instance=urlopen(Request('http://169.254.169.254/latest/meta-data/instance-id',headers={'X-aws-ec2-metadata-token':token}),timeout=3).read().decode()
    if instance!=args.instance_id:raise RuntimeError('instance_mismatch')
    config=json.loads((CONF/'mongod.conf').read_text())
    before=mongo('const h=a.hello();print(JSON.stringify({setName:h.setName||null,primary:h.isWritablePrimary}));')
    if before['setName'] and before['setName']!='ads-rs':raise RuntimeError('different_replica_set_preserved')
    if not args.apply:print(json.dumps({'applied':False,'current':before,'replica_set':'ads-rs','members':1}));return
    # The existing certificate must cover the advertised stable hostname.
    run(['openssl','verify','-CAfile',str(CONF/'tls/ca.crt'),'-verify_hostname','mongodb',str(CONF/'tls/node.crt')])
    try:resolved=socket.gethostbyname('mongodb')
    except socket.gaierror:
        with open('/etc/hosts','a') as stream:stream.write('\n'+runtime['node']['address']+' mongodb\n')
    else:
        if resolved!=runtime['node']['address']:raise RuntimeError('advertised_hostname_mismatch')
    if before['setName']=='ads-rs' and before['primary']:
        print(json.dumps({'applied':False,'already_primary':True,'replica_set':'ads-rs','members':1}));return
    when=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=DATA/'backups'/('replica-'+when);backup.mkdir(parents=True,mode=0o700)
    shutil.copy2(CONF/'mongod.conf',backup/'mongod.conf.before')
    size=int(run(['du','-sb',str(DATA/'data')]).stdout.split()[0])
    if shutil.disk_usage(DATA).free<size+1024**3:raise RuntimeError('insufficient_backup_space')
    run(['systemctl','stop','music-mongodb'])
    try:run(['tar','-czf',str(backup/'data-before.tgz'),'-C',str(DATA),'data'])
    finally:run(['systemctl','start','music-mongodb'])
    keyfile=CONF/'replica.key'
    if not keyfile.exists():save(keyfile,base64.b64encode(secrets.token_bytes(756)).decode()+'\n',user='mongodb')
    config['replication']={'replSetName':'ads-rs','oplogSizeMB':256}
    config['security']['keyFile']=str(keyfile)
    # Keep existing TLS, authentication, users and data path intact.
    save(CONF/'mongod.conf',json.dumps(config,indent=2)+'\n',user='mongodb')
    run(['systemctl','restart','music-mongodb'])
    for _ in range(40):
        try:
            result=mongo("const h=a.hello();if(!h.setName){const r=a.runCommand({replSetInitiate:{_id:'ads-rs',members:[{_id:0,host:'mongodb:'+c.database.port}]}});if(r.ok!==1)quit(3);}print(JSON.stringify({ok:true}));")
            break
        except Exception:time.sleep(1)
    else:raise RuntimeError('replica_initialization_failed_backup_preserved')
    for _ in range(40):
        result=mongo('const h=a.hello();print(JSON.stringify({setName:h.setName||null,primary:h.isWritablePrimary}));')
        if result.get('setName')=='ads-rs' and result.get('primary'):break
        time.sleep(1)
    else:raise RuntimeError('primary_not_elected_backup_preserved')
    save(backup/'result.json',json.dumps({'replica_set':'ads-rs','members':1,'primary':True,'generation':args.generation}))
    print(json.dumps({'replica_set':'ads-rs','members':1,'primary':True,'data_backup_created':True,'tls_and_auth_preserved':True,'high_availability':False}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__,'reason':str(error) if isinstance(error,RuntimeError) else 'see_private_receipt'}));raise SystemExit(1)
