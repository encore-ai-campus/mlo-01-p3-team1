#!/usr/bin/env python3
"""Resume native infrastructure-service setup through SSM; business apps are team-owned."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'bin'),str(ROOT/'lib')]
import install
from awscli import Aws,AwsError
from infra import account,inventory
from manage import write
from project import load
from revision import source_identity


def phases(c):
    nodes=[n for a in c['accounts'] for n in a['nodes']]
    names=lambda role:[n['name'] for n in nodes if n['role']==role]
    core=[n['name'] for n in nodes if n['role'] in install.CORE_ROLES]
    # Complete each group before the next one: three ZK/Masters are a global barrier.
    return [('init-empty-disk',[n['name'] for n in nodes]),('common',core),('check-common',core),
            ('zookeeper',names('spark')),('zookeeper-health',names('spark')),
            ('kafka',names('kafka')),('es',names('es')),('finalize-es',names('es')),
            ('spark-master',names('spark')),('spark-master-health',names('spark')),('spark-worker',names('spark')),
            ('postgresql',names('postgresql')),('mongodb',names('mongodb')),
            ('control',names('control')),('application-host',names('advertising')),
            ('health',names('kafka')+names('spark')+names('es')),
            ('database-health',names('postgresql')+names('mongodb')),
            ('smoke',[names(role)[0] for role in ('kafka','spark','es')])]


def run_step(c,folder,node,stage):
    receipt=folder/(node+'-'+stage+'.json')
    if not receipt.exists():
        install.send(c,node,stage,receipt,c['generation'] if stage=='init-empty-disk' else None)
    record=json.loads(receipt.read_text())
    if record.get('generation')!=c['generation'] or record.get('node')!=node or record.get('stage')!=stage:
        raise ValueError('Setup receipt identity mismatch')
    if not record.get('command_id'):
        raise AwsError('SSM submission outcome unknown; inspect command history before any resubmission')
    if record.get('status')=='Success':
        return
    if record.get('status') in ('Failed','TimedOut','Cancelled','Cancelling'):
        raise AwsError('Previous SSM stage failed; inspect it before an explicit retry')
    aws=Aws(c,account(c,record['profile']))
    try:
        value=install.poll(aws,record['command_id'],record['instance_id'],seconds=14500)
    except AwsError:
        # Preserve command ID. Unknown/time-limited observation never causes resubmission.
        record['observation']='not successful; inspect this command ID before retry'
        write(receipt,record)
        raise
    record['status']=value['Status'];write(receipt,record)


def setup(c,folder,workers=3):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'identity.json';identity={'generation':c['generation'],'source':source_identity()}
    if marker.exists():
        old=json.loads(marker.read_text())
        if old['generation']!=identity['generation'] or old['source']['source_sha256']!=identity['source']['source_sha256']:
            raise ValueError('Setup code/generation changed; use a reviewed upgrade or a new full installation')
    else:write(marker,identity)
    current=inventory(c,folder/'inventory.json');install.checked_inventory(c,current)
    if any(n['state']!='running' or not n['ssm_online'] for n in current['nodes']):
        raise AwsError('All 14 EC2 must be running and SSM Online before service setup')
    packages=install.manifest(c)
    if not packages.exists():install.prepare(c,folder/'inventory.json')
    for package in json.loads(packages.read_text()):
        expected=next(n for n in current['nodes'] if n['name']==package['node'])
        if package['instance_id']!=expected['instance_id'] or package['generation']!=c['generation']:
            raise ValueError('Private setup packages are stale after instance replacement')
        if package.get('implementation',{}).get('source_sha256')!=identity['source']['source_sha256']:
            raise ValueError('Private package code differs; inspect and explicitly prepare fresh packages')
    for stage,nodes in phases(c):
        print('Infrastructure setup: '+stage+' ('+str(len(nodes))+' nodes)',flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            results=list(pool.map(lambda node:run_step(c,folder,node,stage),nodes))
    write(folder/'summary.json',{'generation':c['generation'],'source':source_identity(),
          'scope':'infrastructure-service stages and native smoke checks completed',
          'business_apps':'team deploys and validates applications',
          'connector_dependencies':'Kafka/S3A dependency lock and Spark-ES integration remain separate',
          'control_fencing':'team lifecycle integration and fencing validation remain separate'})
    print('Infrastructure-service setup finished; application deployment/integration/Control fencing are separate',flush=True)


def verify(c,folder,workers=3):
    """A new receipt directory means fresh checks instead of replaying cached setup success."""
    current=inventory(c,Path(folder)/'inventory.json');install.checked_inventory(c,current)
    if any(n['state']!='running' or not n['ssm_online'] for n in current['nodes']):
        raise AwsError('Infrastructure inventory/SSM readiness failed')
    for stage,nodes in phases(c):
        if stage not in ('health','database-health','smoke'):continue
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda node:run_step(c,Path(folder),node,stage),nodes))
    write(Path(folder)/'summary.json',{'generation':c['generation'],'source':source_identity(),
          'scope':'fresh native-service health and Kafka/Spark/ES/DB smoke checks',
          'business_app_flow_and_fencing':'team integration; not evaluated by this command'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--state-dir',required=True)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args();c=load(args.config)
    if not c.get('generation'):raise ValueError('Use the recorded lifecycle config with its actual generation')
    folder=Path(args.state_dir).resolve()
    if not folder.is_relative_to((ROOT/'.state').resolve()):raise ValueError('Setup receipts must stay inside ignored .state')
    if not 1<=args.workers<=5:raise ValueError('workers must be 1..5')
    if not args.execute:
        print(json.dumps({'phases':phases(c),'applications_owner':'team','executed':False},indent=2));return
    raise ValueError('Use aws-project.sh setup --execute so the lifecycle environment lock protects setup/destroy')


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError,AwsError) as error:sys.exit('[FAIL] '+str(error))
