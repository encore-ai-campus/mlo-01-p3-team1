#!/usr/bin/env python3
"""Explicit AWS-only plan, inspection, template generation and per-stack execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
from project import (load,blockers,prefix,stack_name,PROFILES,web_port)
from templates import generate,logical,tags
from awscli import Aws,AwsError,wait_until
from revision import source_identity


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')
    path.chmod(0o600)


def account(c,profile):return next(x for x in c['accounts'] if x['profile']==profile)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owned(stack,c):
    observed={x['Key']:x['Value'] for x in stack.get('Tags',[])}
    return all(observed.get(k)==c[k.lower()] for k in ('Project','Environment'))


def get_stack(aws,name,c):
    try:s=aws.call('cloudformation','describe-stacks','--stack-name',name)['Stacks'][0]
    except AwsError as e:
        if 'does not exist' in str(e):return None
        raise
    if not owned(s,c):raise AwsError('Stack name exists without matching ownership tags; refusing takeover')
    return s


def outputs(aws,name,c):
    s=get_stack(aws,name,c)
    if not s or s['StackStatus'] not in ('CREATE_COMPLETE','UPDATE_COMPLETE','UPDATE_ROLLBACK_COMPLETE'):
        raise AwsError('Dependency stack is not ready: '+name)
    return {x['OutputKey']:x['OutputValue'] for x in s.get('Outputs',[])}


def stack_spec(c,a,kind):
    """Resolve real stack outputs, never use invented EC2/VPC/ENI IDs."""
    admin=kind in ('bootstrap','acceptor')
    aws=Aws(c,a,admin=admin)
    params={};template=stack_name(c,a['profile'],kind)
    if kind=='bootstrap':return aws,template,params,template,True
    if kind=='storage':
        for dep in c['accounts']:
            outputs(Aws(c,dep),stack_name(c,dep['profile'],'bootstrap'),c)
    elif kind=='network':
        needed=blockers(c,'network')
        if needed:raise ValueError('Unresolved network inputs: '+', '.join(needed))
        # Recheck existing CIDRs at execution time; a previously empty account is only a time snapshot.
        current=aws.call('ec2','describe-vpcs')['Vpcs']
        import ipaddress
        existing=get_stack(aws,template,c)
        existing_id=next((o['OutputValue'] for o in existing.get('Outputs',[]) if o['OutputKey']=='VpcId'),None) if existing else None
        for v in current:
            if v['VpcId']!=existing_id and any(ipaddress.ip_network(x['CidrBlock']).overlaps(ipaddress.ip_network(a['cidr']))
                  for x in v.get('CidrBlockAssociationSet',[{'CidrBlock':v['CidrBlock']}]) if x.get('CidrBlock')):
                raise AwsError('VPC CIDR collision: '+v['VpcId'])
        azs=aws.call('ec2','describe-availability-zones')['AvailabilityZones']
        available={z['ZoneId'] for z in azs if z['State']=='available'}
        if not set(c['az_ids'].values())<=available:raise AwsError('Selected physical AZ is unavailable in this account')
        params={'Az'+z.upper():v for z,v in c['az_ids'].items()}
    elif kind=='acceptor':
        if not any(y==a['profile'] for x,y in c['peering_pairs']):raise ValueError('This account has no accepter role')
        params={'VpcId':outputs(aws,stack_name(c,a['profile'],'network'),c)['VpcId']}
    elif kind.startswith('compute-'):
        needed=blockers(c,'compute')
        if needed:raise ValueError('Unresolved compute inputs: '+', '.join(needed))
        n=next(n for n in a['nodes'] if kind=='compute-'+n['name'])
        image=aws.call('ec2','describe-images','--image-ids',c['ami_id'])['Images']
        if len(image)!=1 or image[0]['OwnerId']!='099720109477' or image[0]['Architecture']!='x86_64' or image[0]['State']!='available' or 'ubuntu-noble-24.04' not in image[0]['Name']:
            raise AwsError('AMI is not an available Canonical Ubuntu 24.04 amd64 image')
        ty=aws.call('ec2','describe-instance-types','--instance-types',n['instance_type'])['InstanceTypes'][0]
        if ty.get('Hypervisor')!='nitro' or 'x86_64' not in ty['ProcessorInfo']['SupportedArchitectures']:
            raise AwsError('AWS installer requires Nitro x86_64 to identify data EBS volumes by serial')
        offers=aws.call('ec2','describe-instance-type-offerings','--location-type','availability-zone-id','--filters',json.dumps([{'Name':'instance-type','Values':[n['instance_type']]},{'Name':'location','Values':[c['az_ids'][n['az_slot']]]}]))['InstanceTypeOfferings']
        if not offers:raise AwsError('Selected instance type is not offered in this physical AZ')
        if ty['VCpuInfo']['DefaultVCpus']!=n['cpu'] or ty['MemoryInfo']['SizeInMiB']!=n['memory_mib']:
            raise AwsError('Configured CPU/RAM differs from real EC2 type')
        quota=aws.call('service-quotas','get-service-quota','--service-code','ec2','--quota-code','L-1216C47A')['Quota']['Value']
        # This draft supports standard on-demand families covered by that quota only.
        if not re.fullmatch(r'[acdmrt][0-9][a-z]*\.[a-z0-9]+',n['instance_type']):
            raise AwsError('Instance family requires a different quota workflow; select a standard on-demand family')
        if sum(x['cpu'] for x in a['nodes'])>quota:raise AwsError('Project vCPU plan exceeds account quota')
        net=outputs(aws,stack_name(c,a['profile'],'network'),c)
        params={'AmiId':c['ami_id'],'InstanceType':n['instance_type'],'EniId':net[logical(n['name'])+'EniId'],
                'RootGiB':n['root_gib'],'DataGiB':n['data_gib']}
        eni=aws.call('ec2','describe-network-interfaces','--network-interface-ids',params['EniId'])['NetworkInterfaces'][0]
        if not get_stack(aws,template,c) and (eni['Status']!='available' or eni.get('Attachment')):
            raise AwsError('Primary ENI is still attached; remove old compute and wait before recreation')
    elif kind.startswith('peer-') or kind.startswith('route-'):
        other=kind.split('-',1)[1];peer=account(c,other)
        pair=next(((x,y) for x,y in c['peering_pairs'] if {x,y}=={a['profile'],other}),None)
        if not pair:raise ValueError('Not one of the seven approved peer pairs')
        requester,accepter=map(lambda p:account(c,p),pair)
        src=outputs(Aws(c,requester),stack_name(c,requester['profile'],'network'),c)
        dst=outputs(Aws(c,accepter),stack_name(c,accepter['profile'],'network'),c)
        if kind.startswith('peer-'):
            if a['profile']!=requester['profile']:raise ValueError('Create peering only in the requester account')
            template='peering';params={'VpcId':src['VpcId'],'PeerVpcId':dst['VpcId'],'PeerOwnerId':accepter['account_id'],
                'PeerRoleArn':f"arn:aws:iam::{accepter['account_id']}:role/{prefix(c)}-peering-accepter"}
        else:
            template='route';net=src if a['profile']==requester['profile'] else dst
            pcx=outputs(Aws(c,requester),stack_name(c,requester['profile'],'peer-'+accepter['profile']),c)['PeeringId']
            params={'PeeringId':pcx,'DestinationCidr':peer['cidr'],**{'RouteTable'+z:net['PrivateRouteTable'+z] for z in 'ABC'}}
    elif kind=='alb':
        if a['profile']!='encore1':raise ValueError('ALB belongs to encore1')
        needed=blockers(c,'alb')
        if needed:raise ValueError('Unresolved ALB inputs: '+', '.join(needed))
        import ipaddress
        cidr=ipaddress.ip_network(c['alb']['allowed_client_cidr'])
        if cidr.version!=4 or cidr.prefixlen==0:raise ValueError('ALB client CIDR must be a restricted IPv4 network')
        if c['alb'].get('protocol','HTTPS')=='HTTPS' and not re.fullmatch(r'arn:aws:acm:ap-northeast-2:'+a['account_id']+r':certificate/[a-f0-9-]+',c['alb'].get('certificate_arn') or ''):
            raise ValueError('Select an encore1 Seoul ACM certificate')
        net=outputs(aws,stack_name(c,a['profile'],'network'),c)
        params={'VpcId':net['VpcId'],'PublicSubnetA':net['PublicSubnetA'],'PublicSubnetB':net['PublicSubnetB'],
            'SecurityGroupId':net['AlbSecurityGroupId'],
            'ControlAId':outputs(aws,stack_name(c,a['profile'],'compute-control-a'),c)['InstanceId'],
            'ControlBId':outputs(aws,stack_name(c,a['profile'],'compute-control-b'),c)['InstanceId'],
            'Protocol':c['alb'].get('protocol','HTTPS'),'CertificateArn':c['alb'].get('certificate_arn') or '', 'ClientCidr':str(cidr),'HealthPath':c['alb']['health_path'],
            'TargetPort':web_port(c)}
    else:raise ValueError('Supported kinds: bootstrap, network, storage, acceptor, compute-NODE, peer-PROFILE, route-PROFILE, alb; business apps/Control HA require team integration')
    return aws,stack_name(c,a['profile'],kind),params,template,admin


def inspect(c,out):
    checks=[]
    ops={'identity':('sts','get-caller-identity'),
         'vpcs':('ec2','describe-vpcs'), 'azs':('ec2','describe-availability-zones'),
         'cloudformation':('cloudformation','list-stacks'), 'ssm':('ssm','describe-instance-information'),
         'quota':('service-quotas','get-service-quota','--service-code','ec2','--quota-code','L-1216C47A')}
    for a in c['accounts']:
        try:aws=Aws(c,a,raw=True)
        except AwsError as e:
            checks.append({'profile':a['profile'],'check':'identity','ok':False,'error':str(e)});continue
        for k,args in ops.items():
            try:checks.append({'profile':a['profile'],'check':k,'ok':True,'value':aws.call(*args)})
            except AwsError as e:checks.append({'profile':a['profile'],'check':k,'ok':False,'error':str(e)})
    write(out,checks)
    print(json.dumps([{'profile':r['profile'],'check':r['check'],'ok':r['ok']} for r in checks],indent=2))


def inventory(c,out):
    nodes=[]
    for a in c['accounts']:
        aws=Aws(c,a)
        filters=[{'Name':'tag:'+k,'Values':[c[k.lower()]]} for k in ('Project','Environment')]
        filters.append({'Name':'instance-state-name','Values':['pending','running','stopping','stopped']})
        reservations=aws.call('ec2','describe-instances','--filters',json.dumps(filters))['Reservations']
        observed=[n for r in reservations for n in r['Instances']]
        if len(observed)!=len(a['nodes']):raise AwsError('Unexpected node count in '+a['profile'])
        azs={z['ZoneName']:z['ZoneId'] for z in aws.call('ec2','describe-availability-zones')['AvailabilityZones']}
        online={x['InstanceId'] for x in aws.call('ssm','describe-instance-information')['InstanceInformationList'] if x['PingStatus']=='Online'}
        net=outputs(aws,stack_name(c,a['profile'],'network'),c)
        for expected in a['nodes']:
            found=[n for n in observed if {t['Key']:t['Value'] for t in n['Tags']}.get('Node')==expected['name']]
            if len(found)!=1:raise AwsError('Missing/duplicate node '+expected['name'])
            n=found[0]; tag={x['Key']:x['Value'] for x in n['Tags']}
            az=azs[n['Placement']['AvailabilityZone']]
            primary=next(e for e in n['NetworkInterfaces'] if e['Attachment']['DeviceIndex']==0)
            iid=outputs(aws,stack_name(c,a['profile'],'compute-'+expected['name']),c)['InstanceId']
            if (n['InstanceId']!=iid or primary['NetworkInterfaceId']!=net[logical(expected['name'])+'EniId']
                or tag.get('Role')!=expected['role'] or n['PrivateIpAddress']!=expected['private_ip']
                or az!=c['az_ids'][expected['az_slot']] or n.get('PublicIpAddress')):
                raise AwsError('AWS identity/IP/ENI/role/AZ differs from the node contract')
            nodes.append({**expected,'profile':a['profile'],'account_id':a['account_id'],'instance_id':iid,
                'eni_id':primary['NetworkInterfaceId'],'private_ip':n['PrivateIpAddress'],'az_id':az,
                'data_volume_id':next(b['Ebs']['VolumeId'] for b in n['BlockDeviceMappings'] if b['DeviceName']=='/dev/sdf'),
                'state':n['State']['Name'],'ssm_online':iid in online})
    value={'environment':'aws','project':c['project'],'environment_name':c['environment'],
           'generation':c['generation'],'nodes':nodes}
    write(out,value);print('AWS inventory verified: 14 nodes; service installation has not been inferred.')
    return value


def changeset(c,a,kind,out):
    aws,name,params,template,admin=stack_spec(c,a,kind)
    templates=generate(c,ROOT/'.state/rendered')
    path=ROOT/'.state/rendered'/(template+'.json')
    lint=ROOT/'.tools/validation/bin/cfn-lint';guard=ROOT/'.tools/cfn-guard'
    if not lint.is_file() or not guard.is_file():
        raise ValueError('Approved local cfn-lint/cfn-guard tools are required before change-set creation')
    for cmd in ([str(lint),'-t',str(path),'-r',c['region'],'-f','json'],
                [str(guard),'validate','--rules',str(ROOT/'tests/project.guard'),'--data',str(path),'--output-format','json']):
        checked=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
        if checked.returncode:
            raise ValueError('Local template validation failed: '+path.name+'; run bin/check-local.sh for findings')
    existing=get_stack(aws,name,c)
    token='review-'+uuid.uuid4().hex
    args=['--stack-name',name,'--change-set-name',token,'--change-set-type','UPDATE' if existing else 'CREATE',
          '--template-body','file://'+str(path),'--tags',json.dumps(tags(c))]
    if params:args+=['--parameters',json.dumps([{'ParameterKey':k,'ParameterValue':str(v)} for k,v in params.items()])]
    if admin or kind=='network':args+=['--capabilities','CAPABILITY_NAMED_IAM']
    if not admin:args+=['--role-arn',f"arn:aws:iam::{a['account_id']}:role/{prefix(c)}-cfn-execution"]
    result=aws.call('cloudformation','create-change-set',*args)
    record={'profile':a['profile'],'kind':kind,'stack_name':name,'change_set_id':result['Id'],
            'config_sha256':digest(CONFIG),'template_sha256':digest(path),'admin':admin,'implementation':source_identity()}
    write(out,record)
    state=wait_until(lambda:aws.call('cloudformation','describe-change-set','--change-set-name',result['Id']),
                     lambda s:s['Status'] in ('CREATE_COMPLETE','FAILED'),seconds=300)
    record['status']=state['Status'];record['changes']=state.get('Changes',[]);record['reason']=state.get('StatusReason')
    write(out,record);print(json.dumps(record,indent=2))
    if state['Status']=='FAILED':raise AwsError('Change set failed; inspect saved reason, no resources were executed')


def apply(c,path):
    record=json.loads(Path(path).read_text())
    if record['config_sha256']!=digest(CONFIG):raise ValueError('Config changed since review; create a fresh change set')
    a=account(c,record['profile']);aws=Aws(c,a,admin=record['admin'])
    state=aws.call('cloudformation','describe-change-set','--change-set-name',record['change_set_id'])
    if state['StackName']!=record['stack_name'] or state['Status']!='CREATE_COMPLETE' or state['ExecutionStatus']!='AVAILABLE':
        raise AwsError('Change set is not available for the expected project stack')
    expected=stack_name(c,a['profile'],record['kind'])
    if expected!=state['StackName'] or record['admin']!=(record['kind'] in ('bootstrap','acceptor')):
        raise AwsError('Unexpected stack name or administrator execution mode')
    for change in state.get('Changes',[]):
        r=change['ResourceChange']
        if record['kind'].startswith('compute-') and r['Action'] in ('Modify','Remove'):
            raise AwsError('Existing compute changes require explicit remove/wait/recreate workflow')
        if r.get('Replacement') in ('True','Conditional') and r['ResourceType']=='AWS::EC2::NetworkInterface':
            raise AwsError('Attached stable ENI replacement requires a separate reviewed migration')
    aws.call('cloudformation','execute-change-set','--change-set-name',record['change_set_id'])
    def check():
        s=get_stack(aws,state['StackName'],c)
        if s['StackStatus'].endswith('_FAILED') or s['StackStatus'] in ('ROLLBACK_COMPLETE','UPDATE_ROLLBACK_COMPLETE'):
            raise AwsError('Stack failed/rolled back; inspect cloudformation describe-events')
        execution=aws.call('cloudformation','describe-change-set','--change-set-name',record['change_set_id'])['ExecutionStatus']
        if execution=='EXECUTE_FAILED':raise AwsError('Change set execution failed; inspect describe-events')
        return s,execution
    value,_=wait_until(check,lambda pair:pair[1]=='EXECUTE_COMPLETE' and pair[0]['StackStatus'] in ('CREATE_COMPLETE','UPDATE_COMPLETE'))
    print(json.dumps({'stack':value['StackName'],'status':value['StackStatus'],
                      'service_installation':'not verified'},indent=2))


def remove(c,a,kind,confirm):
    name=stack_name(c,a['profile'],kind)
    if confirm!=name:raise ValueError('--confirm must equal the exact project stack name')
    if not (kind.startswith(('compute-','peer-','route-')) or kind=='network'):
        raise ValueError('This phase supports compute/route/peer/network deletion only; IAM and retained versioned S3 need separate ownership handling')
    aws=Aws(c,a);s=get_stack(aws,name,c)
    if not s:print('Stack already absent');return
    eni=None
    if kind.startswith('compute-'):
        n=next(n for n in a['nodes'] if kind=='compute-'+n['name'])
        if n['role']=='control':raise ValueError('Control stop/fencing pre-delete contract is pending; automatic removal is blocked')
        eni=outputs(aws,stack_name(c,a['profile'],'network'),c)[logical(n['name'])+'EniId']
    elif kind=='network':
        vpc=outputs(aws,name,c)['VpcId']
        attached=aws.call('ec2','describe-network-interfaces','--filters',json.dumps([{'Name':'vpc-id','Values':[vpc]}]))['NetworkInterfaces']
        if any(e.get('Attachment',{}).get('InstanceId') or (e.get('Attachment') and not e.get('RequesterManaged')) for e in attached):
            raise AwsError('Remove compute and wait for ENI detachment before deleting network')
        peers=aws.call('ec2','describe-vpc-peering-connections')['VpcPeeringConnections']
        if any(p['Status']['Code'] not in ('deleted','rejected','expired','failed') and
               vpc in (p['RequesterVpcInfo']['VpcId'],p['AccepterVpcInfo']['VpcId']) for p in peers):
            raise AwsError('Remove reciprocal routes and peering stacks before deleting network')
    aws.call('cloudformation','delete-stack','--stack-name',name,'--role-arn',f"arn:aws:iam::{a['account_id']}:role/{prefix(c)}-cfn-execution")
    def check():
        s=get_stack(aws,name,c)
        if s and s['StackStatus']=='DELETE_FAILED':raise AwsError('Delete failed; inspect dependencies and describe-events')
        return s
    wait_until(check,lambda s:s is None)
    if eni:
        wait_until(lambda:aws.call('ec2','describe-network-interfaces','--network-interface-ids',eni)['NetworkInterfaces'][0],
                   lambda e:e['Status']=='available' and not e.get('Attachment'),seconds=300)
    print('Stack removed'+('; stable ENI is available for explicit recreate' if eni else '')+'. Full project deletion is not complete.')


def plan(c):
    graph=[]
    for kind in ('bootstrap','network','storage'):
        for a in c['accounts']:
            graph.append({'profile':a['profile'],'kind':kind,'admin':kind=='bootstrap'})
    for x,y in c['peering_pairs']:
        graph.extend([{'profile':x,'kind':'peer-'+y},{'profile':x,'kind':'route-'+y},{'profile':y,'kind':'route-'+x}])
    for a in c['accounts']:
        graph += [{'profile':a['profile'],'kind':'compute-'+n['name']} for n in a['nodes']]
    graph.append({'profile':'encore1','kind':'alb'})
    return {'counts':{'accounts':5,'vpcs':5,'ec2':14,'physical_azs':3,'nat_gateways':5,'peerings':7},
            'deployment':'not executed by plan','budget':{**c['budget'],'operating_days':c['budget']['duration_hours']/24,
                'meaning':'Cost estimate for 96h; repeatable create/destroy, no mandatory continuous lifetime',
                'automatic_expiry':'not scheduled; workload exists only until explicit destroy'},'stack_order':graph,'network_blockers':blockers(c,'network'),
            'compute_blockers':blockers(c,'compute'),'pending':['ALB/HTTPS','DB/ad installation','application integration',
                'Control fencing','Spark master/worker coordinated startup','S3A/checkpoint smoke','version-aware S3 purge and full destroy/reinstall verification']}


def main():
    global CONFIG
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default=str(ROOT/'config/project.json'))
    sub=p.add_subparsers(dest='action',required=True)
    for name in ('plan','render'):sub.add_parser(name)
    for name in ('inspect','inventory'):
        q=sub.add_parser(name);q.add_argument('--out',required=True)
    q=sub.add_parser('validate-templates');q.add_argument('--profile',default='encore1')
    q=sub.add_parser('changeset');q.add_argument('--profile',required=True,choices=PROFILES);q.add_argument('--kind',required=True);q.add_argument('--out',required=True)
    q=sub.add_parser('apply');q.add_argument('--review',required=True)
    q=sub.add_parser('remove');q.add_argument('--profile',required=True,choices=PROFILES);q.add_argument('--kind',required=True);q.add_argument('--confirm',required=True)
    a=p.parse_args();CONFIG=Path(a.config).resolve();c=load(CONFIG)
    if a.action=='plan':print(json.dumps(plan(c),indent=2))
    elif a.action=='render':
        target=ROOT/('templates' if c.get('example_only') is True else '.state/rendered')
        print(f'{len(generate(c,target))} CloudFormation templates generated in {target}; no AWS mutation')
    elif a.action=='inspect':inspect(c,a.out)
    elif a.action=='inventory':inventory(c,a.out)
    elif a.action=='validate-templates':
        target=ROOT/'.state/rendered';generate(c,target);aws=Aws(c,account(c,a.profile),raw=True)
        for path in sorted(target.glob('*.json')):
            aws.call('cloudformation','validate-template','--template-body','file://'+str(path))
            print(path.name+': service ValidateTemplate PASS (syntax only)')
    elif a.action=='changeset':changeset(c,account(c,a.profile),a.kind,a.out)
    elif a.action=='apply':apply(c,a.review)
    elif a.action=='remove':remove(c,account(c,a.profile),a.kind,a.confirm)


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,StopIteration,OSError,AwsError) as e:
        print('[FAIL] '+str(e),file=sys.stderr);sys.exit(1)
