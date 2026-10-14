#!/usr/bin/env python3
"""Workstation create/destroy/status for the fixed five-account infrastructure."""
import argparse
import concurrent.futures
import copy
from datetime import datetime,timezone
import fcntl
import hashlib
import ipaddress
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lib'),str(ROOT/'bin')]
from project import load,prefix,stack_name,artifact_bucket,checkpoint_bucket,blockers,web_port
from templates import generate,bootstrap
from awscli import Aws,AwsError,wait_until
from revision import source_identity
import infra

TERMINAL={'CREATE_COMPLETE','UPDATE_COMPLETE'}
DEAD_PEERS={'deleted','rejected','expired','failed'}


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.chmod(0o600);temporary.replace(path)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def accounts(c):return {a['profile']:a for a in c['accounts']}

def workload_steps(c,include_alb=True):
    """Management IAM is installed once, outside the disposable workload graph."""
    steps=[(a['profile'],k) for k in ('network','storage') for a in c['accounts']]
    for x,y in c['peering_pairs']:steps.extend([(x,'peer-'+y),(x,'route-'+y),(y,'route-'+x)])
    steps.extend((a['profile'],'compute-'+n['name']) for a in c['accounts'] for n in a['nodes'])
    if include_alb:steps.append(('encore1','alb'))
    return steps


def teardown_steps(c):
    nodes=[(a['profile'],n) for a in c['accounts'] for n in a['nodes']]
    result=[('encore1','alb')]
    result.extend((p,'compute-'+n['name']) for p,n in nodes if n['role']=='control')
    result.extend((p,'compute-'+n['name']) for p,n in reversed(nodes) if n['role']!='control')
    result.extend((p,'route-'+q) for x,y in reversed(c['peering_pairs']) for p,q in ((x,y),(y,x)))
    result.extend((x,'peer-'+y) for x,y in reversed(c['peering_pairs']))
    # Older deployments may have used separate bindings. Current networks own their binding.
    result.extend((a['profile'],'acceptor') for a in c['accounts'] if a['profile']!='encore1')
    result.extend((a['profile'],'storage') for a in reversed(c['accounts']))
    result.extend((a['profile'],'network') for a in reversed(c['accounts']))
    return result


def owned_bucket_names(c,a):
    return [artifact_bucket(c,a)]+([checkpoint_bucket(c)] if a['profile']=='encore1' else [])


def validate_changes(kind,state):
    for change in state.get('Changes',[]):
        r=change['ResourceChange']
        ingress_change=(kind=='alb' and r.get('LogicalResourceId')=='Ingress' and
                        r.get('ResourceType')=='AWS::EC2::SecurityGroupIngress' and r['Action']=='Modify')
        if r['Action']=='Remove' or (r.get('Replacement') in ('True','Conditional') and not ingress_change):
            raise AwsError('Create/resume will not remove or replace existing resources; destroy the workload first')
        if kind.startswith('compute-') and r['Action']=='Modify':
            raise AwsError('Existing EC2 changes require destroy/recreate to preserve stable ENI sequencing')


def assert_bucket_owned(c,a,name,tags):
    if name not in owned_bucket_names(c,a):raise AwsError('Bucket is outside the project allowlist')
    observed={t['Key']:t['Value'] for t in tags}
    if observed.get('Project')!=c['project'] or observed.get('Environment')!=c['environment']:
        raise AwsError('Bucket ownership tags do not match; refusing purge')


def purge_bucket(aws,c,a,name):
    """Delete versions, delete markers and incomplete uploads. Does not delete the bucket."""
    if name not in owned_bucket_names(c,a):raise AwsError('Bucket outside the project allowlist')
    args=['--bucket',name,'--expected-bucket-owner',a['account_id']]
    try:tags=aws.call('s3api','get-bucket-tagging',*args)['TagSet']
    except AwsError as e:
        if 'NoSuchBucket' in str(e) or '(404)' in str(e):return False
        raise
    assert_bucket_owned(c,a,name,tags)
    while True:
        pending=aws.call('s3api','list-multipart-uploads',*args,'--no-paginate').get('Uploads',[])
        if not pending:break
        for item in pending:aws.call('s3api','abort-multipart-upload',*args,'--key',item['Key'],'--upload-id',item['UploadId'])
    while True:
        page=aws.call('s3api','list-object-versions',*args,'--max-keys','1000','--no-paginate')
        objects=[{'Key':v['Key'],'VersionId':v['VersionId']} for key in ('Versions','DeleteMarkers') for v in page.get(key,[])]
        if not objects:break
        for start in range(0,len(objects),1000):
            # Keep long S3 keys out of argv and terminal output.
            temp=ROOT/'.state'/('delete-objects-'+uuid.uuid4().hex+'.json')
            write(temp,{'Objects':objects[start:start+1000],'Quiet':True})
            try:result=aws.call('s3api','delete-objects',*args,'--delete','file://'+str(temp))
            finally:temp.unlink(missing_ok=True)
            if result.get('Errors'):raise AwsError('S3 version deletion partially failed; no automatic bucket deletion')
    return True


class Manager:
    def __init__(self,c,source,include_alb=True):
        self.source=Path(source).resolve();self.input=copy.deepcopy(c);self.c=c;self.include_alb=include_alb
        self.folder=ROOT/'.state/lifecycle'/prefix(c);self.folder.mkdir(parents=True,exist_ok=True)
        self.current=self.folder/'current.json';self.input_changed=False
        if self.current.exists():
            active=json.loads(self.current.read_text())
            if active['state'] not in ('destroyed','preflight_failed','preparing'):
                self.input_changed=active['source_sha256']!=digest(self.source)
                self.scope_changed=include_alb!=active['include_alb']
                self.c=load(active['resolved_config']);self.run=Path(active['run']);self.include_alb=active['include_alb']
                self.resolved=Path(active['resolved_config'])
                return
        self.run=None;self.resolved=None

    def aws(self,profile):
        # New calls refresh STS sessions as phases advance; long deployments do not keep an expired role session.
        return Aws(self.c,accounts(self.c)[profile])

    def stack(self,profile,kind):return infra.get_stack(self.aws(profile),stack_name(self.c,profile,kind),self.c)

    def start(self):
        generation=self.c.get('generation') or 'g'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M')+'-'+uuid.uuid4().hex[:8]
        self.c=copy.deepcopy(self.c);self.c['generation']=generation
        self.run=self.folder/generation;self.run.mkdir(parents=True,exist_ok=True)
        if self.current.exists():
            prior=json.loads(self.current.read_text())
            if prior['state']=='destroyed' and prior['generation']==generation:
                raise ValueError('A new create after destroy requires a new installation ID; leave generation null for automatic IDs')
        self.resolved=self.run/'config.json';write(self.resolved,self.c)
        write(self.current,{'state':'preparing','run':str(self.run),'resolved_config':str(self.resolved),
            'source_sha256':digest(self.source),'include_alb':self.include_alb,'generation':generation,'implementation':source_identity()})

    def transition(self,state):
        value=json.loads(self.current.read_text());value['state']=state
        value[state+'_at']=datetime.now(timezone.utc).isoformat();write(self.current,value)

    def preflight(self,permission_only=False):
        """Finish every account/permission/input check before the first paid stack."""
        issues=[]
        for a in self.c['accounts']:
            aws=self.aws(a['profile']);s=infra.get_stack(aws,stack_name(self.c,a['profile'],'bootstrap'),self.c)
            if not s or s['StackStatus'] not in TERMINAL:
                issues.append(a['profile']+': bootstrap is not ready');continue
            t=aws.call('cloudformation','get-template','--stack-name',s['StackId'],'--template-stage','Original')['TemplateBody']
            t=json.loads(t) if isinstance(t,str) else t
            expected=bootstrap(self.c,a)
            differing=[k for k,v in expected['Resources'].items() if any(t.get('Resources',{}).get(k,{}).get(key)!=v.get(key) for key in ('Type','Properties'))]
            if differing:issues.append(a['profile']+': one-time bootstrap update needed ('+', '.join(differing)+')')
            if permission_only:continue
            quota=aws.call('service-quotas','get-service-quota','--service-code','ec2','--quota-code','L-1216C47A')['Quota']['Value']
            if sum(n['cpu'] for n in a['nodes'])>quota:issues.append(a['profile']+': insufficient vCPU quota')
            desired=set(v for v in self.c['az_ids'].values() if v)
            available={z['ZoneId'] for z in aws.call('ec2','describe-availability-zones')['AvailabilityZones'] if z['State']=='available'}
            if not desired<=available:issues.append(a['profile']+': selected physical AZ unavailable')
            types=sorted(set(n['instance_type'] for n in a['nodes']))
            descriptions=aws.call('ec2','describe-instance-types','--instance-types',*types)['InstanceTypes']
            sizes={t['InstanceType']:t for t in descriptions}
            for n in a['nodes']:
                t=sizes.get(n['instance_type'],{})
                if t.get('Hypervisor')!='nitro' or t.get('VCpuInfo',{}).get('DefaultVCpus')!=n['cpu'] or t.get('MemoryInfo',{}).get('SizeInMiB')!=n['memory_mib'] or 'x86_64' not in t.get('ProcessorInfo',{}).get('SupportedArchitectures',[]):
                    issues.append(n['name']+': type/CPU/RAM/architecture mismatch')
            if desired:
                offers=aws.call('ec2','describe-instance-type-offerings','--location-type','availability-zone-id','--filters',json.dumps([
                    {'Name':'instance-type','Values':types},{'Name':'location','Values':sorted(desired)}]))['InstanceTypeOfferings']
                offered={(t['InstanceType'],t['Location']) for t in offers}
                for n in a['nodes']:
                    if self.c['az_ids'][n['az_slot']] and (n['instance_type'],self.c['az_ids'][n['az_slot']]) not in offered:
                        issues.append(n['name']+': type not offered in selected physical AZ')
            existing=aws.call('ec2','describe-vpcs')['Vpcs']
            for v in existing:
                tag={t['Key']:t['Value'] for t in v.get('Tags',[])}
                if tag.get('aws:cloudformation:stack-name')==stack_name(self.c,a['profile'],'network'):
                    continue
                if any(ipaddress.ip_network(x['CidrBlock']).overlaps(ipaddress.ip_network(a['cidr'])) for x in v.get('CidrBlockAssociationSet',[{'CidrBlock':v['CidrBlock']}]) if x.get('CidrBlock')):
                    issues.append(a['profile']+': existing VPC CIDR collision')
            if self.c.get('ami_id'):
                images=aws.call('ec2','describe-images','--image-ids',self.c['ami_id'])['Images']
                if len(images)!=1 or images[0].get('OwnerId')!='099720109477' or images[0].get('Architecture')!='x86_64' or images[0].get('State')!='available' or 'ubuntu-noble-24.04' not in images[0].get('Name',''):
                    issues.append(a['profile']+': AMI is not Canonical Ubuntu 24.04 amd64')
        if not permission_only:issues += blockers(self.c,'compute')
        if self.include_alb and not permission_only:
            issues += blockers(self.c,'alb')
            client=self.c['alb'].get('allowed_client_cidr')
            if client and (ipaddress.ip_network(client).version!=4 or ipaddress.ip_network(client).prefixlen==0):issues.append('ALB client network must be restricted IPv4')
            certificate=self.c['alb'].get('certificate_arn')
            if self.c['alb'].get('protocol','HTTPS')=='HTTPS' and certificate:
                pattern=r'arn:aws:acm:ap-northeast-2:'+accounts(self.c)['encore1']['account_id']+r':certificate/[a-f0-9-]+'
                if not re.fullmatch(pattern,certificate):issues.append('ALB certificate must belong to encore1 in Seoul')
                elif self.aws('encore1').call('acm','describe-certificate','--certificate-arn',certificate)['Certificate']['Status']!='ISSUED':
                    issues.append('ALB certificate is not issued')
            if web_port(self.c) is None:
                issues.append('Web target port must be 1..65535')
        if issues:raise ValueError('No paid resources created; preflight needs:\n- '+'\n- '.join(sorted(set(issues))))
        if permission_only:return
        generate(self.c,self.run/'templates')
        lint=ROOT/'.tools/validation/bin/cfn-lint';guard=ROOT/'.tools/cfn-guard'
        if not lint.is_file() or not guard.is_file():raise ValueError('Approved local validation tools are required')
        for cmd in ([str(lint),'-t',*[str(p) for p in (self.run/'templates').glob('*.json')],'-r',self.c['region'],'-f','json'],
                    [str(guard),'validate','--rules',str(ROOT/'tests/project.guard'),'--data',str(self.run/'templates'),'--output-format','json']):
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            if result.returncode:raise ValueError('Local template validation failed; no paid resources created')

    def ensure(self,profile,kind):
        a=accounts(self.c)[profile];aws,name,params,template,admin=infra.stack_spec(self.c,a,kind)
        assert not admin,'Management IAM is not part of create/destroy'
        body=self.run/'templates'/(template+'.json')
        expected=json.loads(body.read_text());s=infra.get_stack(aws,name,self.c)
        record_path=self.run/(profile+'-'+kind+'.json')
        record=json.loads(record_path.read_text()) if record_path.exists() else {}
        if s and s['StackStatus'] in TERMINAL:
            t=aws.call('cloudformation','get-template','--stack-name',name,'--template-stage','Original')['TemplateBody']
            t=json.loads(t) if isinstance(t,str) else t
            observed={p['ParameterKey']:p.get('ParameterValue') for p in s.get('Parameters',[])}
            if t['Resources']==expected['Resources'] and all(observed.get(k)==str(v) for k,v in params.items()):
                print(name+': already ready',flush=True);return
        if kind=='alb' and record.get('status')=='ready':
            archive=record_path.with_name(record_path.stem+'-'+uuid.uuid4().hex+'.json')
            record_path.replace(archive);record={}
        if s and s['StackStatus'].endswith('_IN_PROGRESS'):
            if not record.get('change_set_id'):raise AwsError('Unrecorded stack operation is in progress; inspect before resuming')
        if not record.get('change_set_id'):
            if record.get('status','').startswith('unknown'):
                raise AwsError('Previous create-change-set outcome is unknown; inspect the recorded name before retry')
            if s and s['StackStatus'] not in TERMINAL:raise AwsError('Stack is failed or rolled back; destroy/inspect it before recreate')
            token=record.get('token') or 'lifecycle-'+uuid.uuid4().hex
            record={'token':token,'profile':profile,'kind':kind,'name':name,'status':'change set creation intent','implementation':source_identity()};write(record_path,record)
            args=['--stack-name',name,'--change-set-name',token,'--change-set-type','UPDATE' if s else 'CREATE',
                '--template-body','file://'+str(body),'--tags',json.dumps(infra.tags(self.c)),
                '--role-arn',f"arn:aws:iam::{a['account_id']}:role/{prefix(self.c)}-cfn-execution",'--client-token',token]
            if kind=='network':args+=['--capabilities','CAPABILITY_NAMED_IAM']
            if params:args+=['--parameters',json.dumps([{'ParameterKey':k,'ParameterValue':str(v)} for k,v in params.items()])]
            try:created=aws.call('cloudformation','create-change-set',*args)
            except AwsError:
                record['status']='unknown change set creation outcome; inspect named change set before retry';write(record_path,record);raise
            record['change_set_id']=created['Id'];write(record_path,record)
        cs=wait_until(lambda:aws.call('cloudformation','describe-change-set','--change-set-name',record['change_set_id']),
            lambda x:x['Status'] in ('CREATE_COMPLETE','FAILED'),seconds=600)
        if cs['Status']!='CREATE_COMPLETE':raise AwsError('Change set failed: '+str(cs.get('StatusReason')))
        if cs['StackName']!=name:raise AwsError('Change set stack mismatch')
        validate_changes(kind,cs)
        if cs['ExecutionStatus']=='AVAILABLE':
            events=aws.call('cloudformation','describe-events','--change-set-name',record['change_set_id'])
            if any(e.get('EventType')=='VALIDATION_ERROR' for e in events.get('OperationEvents',[])):
                raise AwsError('CloudFormation validation findings require review; not executing')
            if record.get('execution_requested'):raise AwsError('Previous execute outcome is unknown; inspect rather than resubmit')
            record['execution_requested']=True;write(record_path,record)
            aws.call('cloudformation','execute-change-set','--change-set-name',record['change_set_id'],'--client-request-token',record['token'])
        def ready():
            current=infra.get_stack(aws,name,self.c)
            status=aws.call('cloudformation','describe-change-set','--change-set-name',record['change_set_id'])['ExecutionStatus']
            if not current or 'FAILED' in current['StackStatus'] or 'ROLLBACK' in current['StackStatus'] or status=='EXECUTE_FAILED':
                raise AwsError('Stack deployment failed; state is retained for inspect/destroy')
            return current,status
        wait_until(ready,lambda pair:pair[0]['StackStatus'] in TERMINAL and pair[1]=='EXECUTE_COMPLETE',seconds=3600)
        record['status']='ready';write(record_path,record);print(name+': ready',flush=True)

    def create(self):
        if self.input_changed:raise ValueError('Active input changed; destroy the recorded workload before creating with different inputs')
        if getattr(self,'scope_changed',False):raise ValueError('Active ALB scope differs; use the same flag or destroy before changing scope')
        if self.current.exists() and json.loads(self.current.read_text())['state']=='destroying':
            raise ValueError('Finish destroy before creating a new installation')
        if not self.run:self.start()
        if self.c['generation']!=load(self.resolved)['generation']:raise ValueError('Generation changed')
        initial_state=json.loads(self.current.read_text())['state']
        try:self.preflight()
        except Exception:
            if initial_state in ('preparing','preflight_failed'):self.transition('preflight_failed')
            raise
        infra.CONFIG=self.resolved
        self.transition('creating')
        for profile,kind in workload_steps(self.c,self.include_alb):self.ensure(profile,kind)
        # This checks all 14 identities/ENIs and waits for SSM. It does not install applications.
        def ready():
            try:return infra.inventory(self.c,self.run/'inventory.json')
            except AwsError as e:
                if 'SSM' not in str(e):raise
                return None
        inv=wait_until(ready,lambda v:v is not None and all(n['ssm_online'] for n in v['nodes']),seconds=1200)
        if not all(n['ssm_online'] for n in inv['nodes']):raise AwsError('SSM agents are not ready')
        self.transition('ready');print('Infrastructure ready: 5 VPC, 14 EC2, 7 direct peerings; software is not installed.',flush=True)

    def add_alb(self):
        """Controlled ALB addition/protocol update; preserves core inputs and generation."""
        if not self.current.exists() or not self.run:
            raise ValueError('Create and verify the core infrastructure first')
        active=json.loads(self.current.read_text())
        if active['state'] not in ('ready','adding_alb'):
            raise ValueError('ALB extension requires a ready core or a resumable ALB extension')
        if self.input.get('generation') not in (None,self.c['generation']):
            raise ValueError('ALB extension cannot change installation generation')
        wanted=copy.deepcopy(self.input);wanted['generation']=self.c['generation']
        old=copy.deepcopy(self.c)
        wanted_without=copy.deepcopy(wanted);old_without=copy.deepcopy(old)
        wanted_without.pop('alb');old_without.pop('alb')
        if wanted_without!=old_without:
            raise ValueError('add-alb allows only ALB settings; core ports/specs/topology must remain unchanged')
        if active['include_alb'] and not self.input_changed:
            print('ALB is already recorded; application target health remains separate',flush=True);return
        extension=active.get('alb_extension')
        if extension and extension['source_sha256']!=digest(self.source):
            raise ValueError('Pending ALB extension inputs changed; inspect saved state before retrying')
        self.c=wanted;self.include_alb=True
        self.preflight()
        candidate=self.run/('config-with-alb-'+digest(self.source)[:16]+'.json')
        write(candidate,self.c)
        active['state']='adding_alb'
        active['alb_extension']={'source_sha256':digest(self.source),'resolved_config':str(candidate)}
        write(self.current,active)
        infra.CONFIG=candidate
        self.ensure('encore1','alb')
        active.update(state='ready',include_alb=True,resolved_config=str(candidate),source_sha256=digest(self.source),
                      alb_added_at=datetime.now(timezone.utc).isoformat())
        active.pop('alb_extension',None);write(self.current,active)
        self.resolved=candidate
        print('ALB configuration applied to the existing core; application deployment and target health are separate',flush=True)

    def delete_stack(self,profile,kind):
        aws=self.aws(profile);name=stack_name(self.c,profile,kind);s=infra.get_stack(aws,name,self.c)
        record_path=self.run/('delete-'+profile+'-'+kind+'.json')
        record=json.loads(record_path.read_text()) if record_path.exists() else {}
        if not s:return record.get('instance_id')
        if kind.startswith('compute-') and not record.get('instance_id'):
            resources=aws.call('cloudformation','list-stack-resources','--stack-name',name)['StackResourceSummaries']
            instances=[r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::EC2::Instance' and r.get('PhysicalResourceId')]
            if len(instances)>1:raise AwsError('Unexpected EC2 ownership in a node stack')
            if instances:record['instance_id']=instances[0]
        if s['StackStatus']!='DELETE_IN_PROGRESS':
            if record.get('delete_requested'):raise AwsError('Previous delete outcome is unknown; inspect before retry')
            record.update(delete_requested=True,stack_id=s['StackId']);write(record_path,record)
            aws.call('cloudformation','delete-stack','--stack-name',s['StackId'],
                '--role-arn',f"arn:aws:iam::{accounts(self.c)[profile]['account_id']}:role/{prefix(self.c)}-cfn-execution")
        def gone():
            current=infra.get_stack(aws,name,self.c)
            if current and current['StackStatus']=='DELETE_FAILED':raise AwsError('Stack deletion failed; inspect/resume after correcting dependencies')
            return current
        wait_until(gone,lambda s:s is None,seconds=3600)
        record['status']='deleted';write(record_path,record);print(name+': deleted',flush=True)
        return record.get('instance_id')

    def wait_terminated(self,profile,iid):
        if not iid:return
        aws=self.aws(profile)
        def check():
            try:reservations=aws.call('ec2','describe-instances','--instance-ids',iid)['Reservations']
            except AwsError as e:
                if 'InvalidInstanceID.NotFound' in str(e):return True
                raise
            nodes=[n for r in reservations for n in r['Instances']]
            return not nodes or all(n['State']['Name']=='terminated' for n in nodes)
        wait_until(check,bool,seconds=1200)

    def discover(self):
        result={};allowed=set(workload_steps(self.c,True))|set(teardown_steps(self.c))
        for a in self.c['accounts']:
            aws=self.aws(a['profile']);summaries=aws.call('cloudformation','list-stacks')['StackSummaries']
            known={stack_name(self.c,p,k) for p,k in allowed if p==a['profile']}
            management=stack_name(self.c,a['profile'],'bootstrap')
            names=[s['StackName'] for s in summaries if s['StackStatus']!='DELETE_COMPLETE' and s['StackName'].startswith(prefix(self.c)+'-'+a['profile']+'-')]
            unknown=set(names)-known-{management}
            if unknown:raise AwsError('Unknown project stack; refusing partial full teardown: '+', '.join(sorted(unknown)))
            for name in names:
                if name!=management:infra.get_stack(aws,name,self.c) # ownership preflight before any deletion
            result[a['profile']]=names
        return result

    def destroy(self,confirm):
        if confirm!=prefix(self.c):raise ValueError('--confirm must equal '+prefix(self.c))
        if not self.run:self.start()
        self.preflight(permission_only=True)
        self.discover();self.transition('destroying')
        nodes={n['name']:(a['profile'],n) for a in self.c['accounts'] for n in a['nodes']}
        for profile,kind in teardown_steps(self.c):
            if kind=='storage':
                a=accounts(self.c)[profile]
                # Controls and all data nodes were terminated before checkpoint deletion.
                for name in owned_bucket_names(self.c,a):purge_bucket(self.aws(profile),self.c,a,name)
            iid=self.delete_stack(profile,kind)
            if kind.startswith('compute-'):
                # In particular, both Controls are confirmed terminated before any surviving data cluster is removed.
                self.wait_terminated(profile,iid)
            if kind=='storage':
                a=accounts(self.c)[profile]
                for name in owned_bucket_names(self.c,a):
                    aws=self.aws(profile)
                    try:
                        tags=aws.call('s3api','get-bucket-tagging','--bucket',name,'--expected-bucket-owner',a['account_id'])['TagSet']
                        assert_bucket_owned(self.c,a,name,tags)
                        aws.call('s3api','delete-bucket','--bucket',name,'--expected-bucket-owner',a['account_id'])
                    except AwsError as e:
                        if 'NoSuchBucket' not in str(e) and '(404)' not in str(e):raise
        remaining=wait_until(self.residuals,lambda v:not any(v.values()),seconds=1200,interval=15)
        write(self.run/'remaining.json',remaining)
        if any(remaining.values()):raise AwsError('Workload resources remain; inspect .state before declaring destroy complete')
        self.transition('destroyed');print('Workload destroyed and residuals checked; management IAM is ready for the next create.',flush=True)

    def residuals(self):
        result={};discovered=self.discover()
        for a in self.c['accounts']:
            aws=self.aws(a['profile']);filters=json.dumps([{'Name':'tag:Project','Values':[self.c['project']]},{'Name':'tag:Environment','Values':[self.c['environment']]}])
            entries=[]
            for operation,key in [('describe-vpcs','Vpcs'),('describe-nat-gateways','NatGateways'),('describe-network-interfaces','NetworkInterfaces'),
                                  ('describe-addresses','Addresses'),('describe-volumes','Volumes')]:
                values=aws.call('ec2',operation,'--filter' if operation=='describe-nat-gateways' else '--filters',filters)[key]
                live=[v for v in values if v.get('State')!='deleted']
                if live:entries.append(operation+': '+str(len(live)))
            reservations=aws.call('ec2','describe-instances','--filters',filters)['Reservations']
            if any(n['State']['Name']!='terminated' for r in reservations for n in r['Instances']):entries.append('EC2 remains')
            peers=aws.call('ec2','describe-vpc-peering-connections','--filters',filters)['VpcPeeringConnections']
            if any(p['Status']['Code'] not in DEAD_PEERS for p in peers):entries.append('peering remains')
            for name in owned_bucket_names(self.c,a):
                try:aws.call('s3api','head-bucket','--bucket',name,'--expected-bucket-owner',a['account_id']);entries.append('bucket remains: '+name)
                except AwsError as e:
                    if 'NoSuchBucket' not in str(e) and '(404)' not in str(e):raise
            if a['profile']=='encore1':
                lbs=aws.call('elbv2','describe-load-balancers')['LoadBalancers']
                groups=aws.call('elbv2','describe-target-groups')['TargetGroups']
                if any(lb['LoadBalancerName']==prefix(self.c)+'-web' for lb in lbs):entries.append('ALB remains')
                if any(g['TargetGroupName']==prefix(self.c)+'-web' for g in groups):entries.append('target group remains')
            names=discovered[a['profile']]
            if any(n!=stack_name(self.c,a['profile'],'bootstrap') for n in names):entries.append('workload stack remains')
            result[a['profile']]=entries
        if self.run:write(self.run/'remaining.json',result)
        return result

    def status(self):
        summaries=self.discover()
        state=json.loads(self.current.read_text()) if self.current.exists() else {'state':'not created'}
        print(json.dumps({'lifecycle':state,'stacks':summaries,'budget_duration_hours':self.c['budget']['duration_hours'],
            'meaning':'96h is a cost-estimate assumption; create/destroy can be repeated','applications':'not verified'},indent=2))


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default=str(ROOT/'config/project.json'))
    commands=p.add_subparsers(dest='action',required=True)
    commands.add_parser('plan');commands.add_parser('status')
    commands.add_parser('readiness',help='Offline preparation checks; no AWS calls or lifecycle changes')
    q=commands.add_parser('preflight');q.add_argument('--without-alb',action='store_true');q.add_argument('--resolve-inputs',action='store_true');q.add_argument('--connected-cidr',action='append',default=[])
    q=commands.add_parser('create');q.add_argument('--execute',action='store_true');q.add_argument('--without-alb',action='store_true')
    q=commands.add_parser('add-alb');q.add_argument('--execute',action='store_true')
    q=commands.add_parser('setup');q.add_argument('--execute',action='store_true')
    q=commands.add_parser('verify');q.add_argument('--execute',action='store_true')
    q=commands.add_parser('destroy');q.add_argument('--confirm',required=True)
    a=p.parse_args();c=load(a.config)
    if a.action=='readiness':
        from readiness import check
        report=check(c)
        write(ROOT/'.state/readiness/latest.json',report)
        print(json.dumps(report,indent=2))
        return 0 if report['ready_for_aws_preflight'] else 1
    if a.action=='preflight':
        cmd=[sys.executable,str(ROOT/'bin/preflight.py'),'--config',str(Path(a.config).resolve())]
        if a.resolve_inputs:cmd.append('--resolve-inputs')
        if a.without_alb:cmd.append('--without-alb')
        for cidr in a.connected_cidr:cmd.extend(['--connected-cidr',cidr])
        if subprocess.run(cmd).returncode:
            raise ValueError('Read-only preflight did not pass; inspect .state/preflight/latest.json')
        return
    if a.action=='plan':
        print(json.dumps({'create_order':workload_steps(c),'destroy_order':teardown_steps(c),
            'persistent_prerequisite':'IAM bootstrap and Mac encore profiles','duration_hours':c['budget']['duration_hours'],
            'duration_meaning':'Estimate only; infrastructure can be repeatedly created/destroyed',
            'compute_inputs':[v for v in blockers(c,'compute') if not (c.get('generation') is None and v.startswith('generation '))],'alb_inputs':blockers(c,'alb'),'paid_resources_created':False},indent=2));return
    folder=ROOT/'.state/lifecycle'/prefix(c);folder.mkdir(parents=True,exist_ok=True)
    with (folder/'lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another lifecycle operation is active for this environment')
        manager=Manager(c,a.config,not getattr(a,'without_alb',False))
        if a.action=='create':
            if not a.execute:raise ValueError('Use plan to review, then create --execute to provision')
            manager.create()
        elif a.action in ('setup','verify'):
            if not manager.current.exists() or not manager.run:raise ValueError('Create and verify infrastructure first')
            if manager.input_changed:raise ValueError('Active config changed; reconcile ALB settings or use a reviewed new installation')
            if json.loads(manager.current.read_text())['state']!='ready':raise ValueError('Infrastructure must be ready before service setup')
            import importlib.util
            spec=importlib.util.spec_from_file_location('setup_services',ROOT/'bin/setup-services.py')
            setup_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup_module)
            if a.execute:
                if a.action=='setup':setup_module.setup(manager.c,manager.run/'setup-services')
                else:setup_module.verify(manager.c,manager.run/'verifications'/('v'+uuid.uuid4().hex))
            else:print(json.dumps({'phases':setup_module.phases(manager.c),'executed':False},indent=2))
        elif a.action=='add-alb':
            if not a.execute:raise ValueError('Review ALB settings, then use add-alb --execute')
            manager.add_alb()
        elif a.action=='destroy':manager.destroy(a.confirm)
        else:manager.status()


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,KeyError,OSError,AwsError) as e:sys.exit('[FAIL] '+str(e))
