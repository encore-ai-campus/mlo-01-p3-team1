#!/usr/bin/env python3
"""Prepare node-private AWS packages and explicitly dispatch/resume one SSM stage."""
import argparse
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import shlex
import sys
import tarfile
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lib'),str(ROOT/'installer')]
from project import load,blockers,prefix,artifact_bucket,checkpoint_bucket,checkpoint_prefix
from awscli import Aws,AwsError,wait_until
from revision import source_identity
from infra import inventory,account,write
import database_config

CORE_ROLES={'kafka','spark','es','control'}
STAGES={'preflight','init-empty-disk','common','check-common','kafka','zookeeper','es','control',
        'connectors','health','smoke','finalize-es','catalog','zookeeper-health',
        'spark-master','spark-master-health','spark-worker','postgresql','mongodb','database-health','application-host','checkpoint-smoke','control-fencing'}
AWS_FILES=('aws-bootstrap.sh','aws-identity.py','init-disk.py','spark-master-health.py','control-tools.sh','database.py','database_config.py','application-host.sh','connectors.lock.json','checkpoint_probe.py','integration_scope.py','checkpoint-probe.sh')


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_inventory(c,value):
    if any(value.get(k)!=v for k,v in {'environment':'aws','project':c['project'],
          'environment_name':c['environment'],'generation':c['generation']}.items()):
        raise ValueError('Inventory project/environment/generation mismatch')
    expected={n['name']:(a,n) for a in c['accounts'] for n in a['nodes']}
    if len(value['nodes'])!=14 or {n['name'] for n in value['nodes']}!=set(expected):
        raise ValueError('Fresh inventory must contain exactly the 14 configured logical nodes')
    for n in value['nodes']:
        a,wanted=expected[n['name']]
        if (n['account_id']!=a['account_id'] or n['profile']!=a['profile'] or n['role']!=wanted['role']
            or n['private_ip']!=wanted['private_ip'] or n['az_id']!=c['az_ids'][wanted['az_slot']]
            or not n['instance_id'].startswith('i-') or not n['data_volume_id'].startswith('vol-')):
            raise ValueError('Inventory node identity differs from configuration')


def safe_members(paths):
    for rel,path in paths:
        if Path(rel).is_absolute() or '..' in Path(rel).parts or path.is_symlink() or not path.is_file():
            raise ValueError('Unsafe package member')
        if Path(rel).name=='ca.key':raise ValueError('CA private key must never enter any upload package')
        yield rel,path


def core_inventory(value):
    nodes=[]
    for n in value['nodes']:
        if n['role'] not in CORE_ROLES:continue
        node={**n,'roles':[n['role']],'address':n['private_ip'],'az':n['az_id']}
        if n['role']=='kafka':node['id']=int(n['name'][-2:])
        if n['role']=='spark':node['zk_id']=int(n['name'][-2:])
        nodes.append(node)
    return {'environment':'aws','nodes':nodes}


def prepare(c,inv_path,connector_bundle=None):
    needed=blockers(c,'install')
    if needed:raise ValueError('Select deployment inputs before private package creation: '+', '.join(needed))
    connector_lock=None
    if connector_bundle is not None:
        sys.path.insert(0,str(ROOT/'installer/core/lib'))
        import connectors
        connectors.validate_bundle(connector_bundle,reviewed_lock=ROOT/'installer/connectors.lock.json')
        connector_lock=file_hash(ROOT/'installer/connectors.lock.json')
    value=json.loads(Path(inv_path).read_text());checked_inventory(c,value)
    private=ROOT/'.private'/c['environment']/c['generation'];private.mkdir(parents=True,exist_ok=True);private.chmod(0o700)
    marker={'project':c['project'],'environment':c['environment'],'generation':c['generation']}
    identity=private/'identity.json'
    if identity.exists() and json.loads(identity.read_text())!=marker:raise ValueError('Private generation identity mismatch')
    if not identity.exists():write(identity,marker)
    sys.path.insert(0,str(ROOT/'installer/core/lib'))
    config=importlib.import_module('config');pki=importlib.import_module('pki')
    env=private/'secrets.env'
    if not env.exists():
        values={'ENVIRONMENT':'aws','KAFKA_CLUSTER_ID':base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip('='),
            'AWS_REGION':c['region'],'S3_BUCKET':checkpoint_bucket(c),'S3_CHECKPOINT_PREFIX':checkpoint_prefix(c)}
        values.update({k:secrets.token_urlsafe(32) for k in (*config.SECRET_KEYS,*database_config.SECRET_KEYS)})
        config.write_private(env,''.join(k+'='+v+'\n' for k,v in values.items()))
    old=config.load_env(env)
    if not set(database_config.SECRET_KEYS)<=set(old):
        raise ValueError('Private generation predates database secrets; preserve it and prepare a new generation explicitly')
    if old.get('S3_CHECKPOINT_PREFIX')!=checkpoint_prefix(c):raise ValueError('Checkpoint generation differs; do not reuse old Kafka checkpoint implicitly')
    inv=private/'core.inventory.json';write(inv,core_inventory(value))
    cfg=config.load(env,inv,stage='all')
    pki.prepare({'env':cfg['env'],'inventory':{'nodes':[{**n,'address':n['private_ip'],'roles':[n['role']]} for n in value['nodes']]}},private/'pki')
    db_versions=json.loads((ROOT/'installer/databases.versions.json').read_text())
    manifest=[]
    for n in value['nodes']:
        if n['role'] not in CORE_ROLES|database_config.KINDS|{'advertising'}:continue
        a=account(c,n['profile']);tmp=private/'payloads'/n['name'];tmp.mkdir(parents=True,exist_ok=True)
        if n['role'] in database_config.KINDS:
            runtime=database_config.runtime(c,n,old,db_versions)
        elif n['role']=='advertising':
            runtime={'node':{**n,'address':n['private_ip'],'roles':['app']},'env':{'ENVIRONMENT':'aws','AWS_REGION':c['region']}}
        else:runtime=config.runtime(cfg,n['name'])
        runtime['aws']=marker
        if n['role'] in ('control','advertising'):
            runtime['database_client']=database_config.client(c,old,'postgresql' if n['role']=='control' else 'mongodb')
        write(tmp/'runtime.json',runtime)
        paths=[(f'core/{p.relative_to(ROOT/"installer/core")}',p) for p in (ROOT/'installer/core').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        paths += [(name,ROOT/'installer'/name) for name in AWS_FILES]
        paths += [('runtime.json',tmp/'runtime.json'),('core/pki/ca.crt',private/'pki/ca.crt'),
                  ('core/pki/node.key',private/'pki'/n['name']/'node.key'),('core/pki/node.crt',private/'pki'/n['name']/'node.crt')]
        if connector_bundle is not None and n['role'] in ('spark','control'):
            folder=Path(connector_bundle)
            paths += [('core/connectors/connectors.lock.json',folder/'connectors.lock.json')]
            paths += [('core/connectors/'+j['filename'],folder/j['filename']) for j in json.loads((folder/'connectors.lock.json').read_text())['jars']]
        archive=tmp/'payload.tgz'
        with tarfile.open(archive,'w:gz') as tar:
            for rel,path in safe_members(paths):
                info=tar.gettarinfo(str(path),arcname=rel);info.uid=info.gid=0;info.uname=info.gname='root';info.mode=0o600
                with path.open('rb') as f:tar.addfile(info,f)
        checksum=file_hash(archive);key=f"private/{n['name']}/{c['generation']}/{checksum}/payload.tgz"
        manifest.append({'implementation':source_identity(),'node':n['name'],'profile':n['profile'],'instance_id':n['instance_id'],
            'generation':c['generation'],'file':str(archive),'sha256':checksum,'bucket':artifact_bucket(c,a),'key':key,
            'connector_lock_sha256':connector_lock if n['role'] in ('spark','control') else None})
    write(private/'packages.json',manifest)
    print(f'{len(manifest)} node-private packages prepared. CA key remains on Mac; no S3 upload or EC2 installation performed. Advertising application deployment belongs to the team.')


def stage_allowed(stage,node):
    if node['role']=='advertising':return stage in ('init-empty-disk','preflight','application-host')
    if stage=='application-host':return node['role']=='control'
    if node['role'] in database_config.KINDS:
        return stage in ('init-empty-disk','preflight','database-health',node['role'])
    if stage in ('postgresql','mongodb','database-health'):return False
    required={'kafka':'kafka','es':'es','finalize-es':'es','zookeeper':'spark','spark-master':'spark',
              'spark-worker':'spark','spark-master-health':'spark','zookeeper-health':'spark','control':'control',
              'connectors':('spark','control'),'checkpoint-smoke':'spark','control-fencing':'control'}
    roles=required.get(stage)
    return roles is None or node['role'] in ([roles] if isinstance(roles,str) else roles)


def manifest(c):return ROOT/'.private'/c['environment']/c['generation']/'packages.json'


def send(c,node,stage,receipt,init_token,package_manifest=None):
    if Path(receipt).exists():raise ValueError('Receipt exists; inspect its CommandId with status instead of resubmitting')
    selected_manifest=manifest(c) if package_manifest is None else Path(package_manifest)
    if package_manifest is not None:
        allowed=ROOT/'.private'/c['environment']/c['generation']/'control-fencing'
        if stage!='control-fencing' or not selected_manifest.resolve().is_relative_to(allowed.resolve()):
            raise ValueError('Separate manifests are limited to prepared Control fencing packages')
    if stage in ('connectors','checkpoint-smoke'):
        prepared=next(p for p in json.loads(selected_manifest.read_text()) if p['node']==node)
        if prepared.get('connector_lock_sha256')!=file_hash(ROOT/'installer/connectors.lock.json'):
            raise ValueError('Reviewed connector bundle not explicitly included in this node package; activation blocked')
    if stage=='control-fencing':
        prepared=next(p for p in json.loads(selected_manifest.read_text()) if p['node']==node)
        if prepared.get('control_fencing_lock_sha256')!=file_hash(ROOT/'installer/control-fencing.lock.json'):
            raise ValueError('Explicitly prepared fencing runtime bundle required; ordinary packages cannot activate it')
    with tempfile.TemporaryDirectory() as temp:
        current=inventory(c,Path(temp)/'inventory.json')
    checked_inventory(c,current)
    actual=next(n for n in current['nodes'] if n['name']==node)
    if actual['role'] not in CORE_ROLES|database_config.KINDS|{'advertising'} or not stage_allowed(stage,actual):raise ValueError('Stage not supported for this node role')
    if actual['state']!='running' or not actual['ssm_online']:raise AwsError('Node must be running and SSM Online')
    package=next(p for p in json.loads(selected_manifest.read_text()) if p['node']==node)
    if package.get('implementation',{}).get('source_sha256')!=source_identity()['source_sha256']:
        raise ValueError('Package code differs from current source; explicitly prepare fresh packages')
    if package['instance_id']!=actual['instance_id'] or package['generation']!=c['generation']:
        raise ValueError('Package is stale after EC2 replacement; explicitly prepare against fresh inventory')
    if stage=='init-empty-disk' and init_token!=c['generation']:raise ValueError('--new-generation must equal this explicit generation')
    if file_hash(package['file'])!=package['sha256']:raise ValueError('Private package hash changed')
    aws=Aws(c,account(c,actual['profile']))
    # SSM command parameters contain only paths/hashes/IDs, never credentials or runtime secrets.
    aws.call('s3api','put-object','--bucket',package['bucket'],'--key',package['key'],
             '--body',package['file'],'--server-side-encryption','AES256')
    work=f"/var/lib/music-aws-download/{node}/{c['generation']}/{package['sha256']}"
    ensure='umask 077; install -d -m 0700 /var/lib/music-aws-download '+shlex.quote(work)
    first=aws.call('ssm','send-command','--instance-ids',actual['instance_id'],'--document-name','AWS-RunShellScript',
        '--parameters',json.dumps({'commands':[ensure],'executionTimeout':['60']}))['Command']['CommandId']
    poll(aws,first,actual['instance_id'])
    command=('umask 077; printf %s '+shlex.quote(package['sha256']+'  payload.tgz\n')+' | sha256sum --check --status'
             ' && mkdir -p package && tar --extract --gzip --file payload.tgz --directory package --no-same-owner'
             ' && bash package/aws-bootstrap.sh '+shlex.quote(stage))
    if stage=='init-empty-disk':command+=' '+shlex.quote(init_token)
    params={'sourceType':['S3'],'sourceInfo':[json.dumps({'path':f"https://{package['bucket']}.s3.{c['region']}.amazonaws.com/{package['key']}"})],
        'commandLine':[command],'workingDirectory':[work],'executionTimeout':['14400']}
    write(receipt,{'implementation':source_identity(),'profile':actual['profile'],'node':node,'stage':stage,'generation':c['generation'],
                   'status':'submission intent; if outcome is unknown inspect SSM before any resubmission'})
    result=aws.call('ssm','send-command','--instance-ids',actual['instance_id'],
        '--document-name','AWS-RunRemoteScript','--parameters',json.dumps(params))['Command']
    record={'implementation':source_identity(),'command_id':result['CommandId'],'instance_id':actual['instance_id'],'profile':actual['profile'],
            'node':node,'stage':stage,'generation':c['generation'],'status':'submitted','scope':'single stage; pipeline/HA not verified'}
    write(receipt,record);print(json.dumps(record,indent=2))
    # Dispatch is asynchronous. 'status' waits explicitly using the stored ID; never resend on timeout.


def command_invocation(aws,command,iid):
    # Observe the whole invocation: AWS document step names differ, and remote
    # scripts also have a download step whose result must not be ignored.
    items=aws.call('ssm','list-command-invocations','--command-id',command,
                   '--instance-id',iid,'--details')['CommandInvocations']
    if not items:return {'Status':'Pending'}
    if len(items)!=1 or items[0]['CommandId']!=command or items[0]['InstanceId']!=iid:
        raise AwsError('SSM invocation identity differs from the saved command and instance')
    return items[0]


def poll(aws,command,iid,seconds=300):
    value=wait_until(lambda:command_invocation(aws,command,iid),
        lambda v:v['Status'] not in ('Pending','InProgress','Delayed','Cancelling'),seconds=seconds)
    if value['Status']!='Success':raise AwsError('SSM stage '+value['Status']+'; inspect private logs, no automatic resubmission')
    return value


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default=str(ROOT/'config/project.json'))
    s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('prepare');q.add_argument('--inventory',required=True);q.add_argument('--connector-bundle')
    q=s.add_parser('send');q.add_argument('--node',required=True);q.add_argument('--stage',choices=sorted(STAGES),required=True)
    q.add_argument('--receipt',required=True);q.add_argument('--new-generation')
    q=s.add_parser('status');q.add_argument('--receipt',required=True)
    a=p.parse_args();c=load(a.config)
    if a.action=='prepare':prepare(c,a.inventory,a.connector_bundle)
    elif a.action=='send':send(c,a.node,a.stage,a.receipt,a.new_generation)
    elif a.action=='status':
        r=json.loads(Path(a.receipt).read_text())
        if r['generation']!=c['generation']:raise ValueError('Receipt belongs to another installation generation')
        if 'command_id' not in r:raise ValueError('Submission outcome unknown; inspect SSM command history, do not automatically resend')
        aws=Aws(c,account(c,r['profile']))
        # One bounded read; calling this command again does not install anything again.
        v=command_invocation(aws,r['command_id'],r['instance_id'])
        r['status']=v['Status'];write(a.receipt,r);print(json.dumps(r,indent=2))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,StopIteration,AwsError) as e:sys.exit('[FAIL] '+str(e))
