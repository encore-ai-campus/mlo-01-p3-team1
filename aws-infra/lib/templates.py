"""Generate reviewable CloudFormation JSON using only Python's standard library."""
import json
import os
from pathlib import Path
from project import (account_ids, prefix, stack_name, role_name, artifact_bucket,
                     checkpoint_bucket, subnet_cidr, checkpoint_prefix, web_port)


def ref(name): return {'Ref': name}
def sub(value): return {'Fn::Sub': value}
def attr(name, key='Arn'): return {'Fn::GetAtt': [name, key]}
def logical(name): return ''.join(p.capitalize() for p in name.split('-'))
def doc(statements): return {'Version': '2012-10-17', 'Statement': statements}
def allow(actions, resources, **kw):
    return {'Effect': 'Allow', 'Action': actions, 'Resource': resources, **kw}
def trust(service):
    # EC2/CloudFormation role assumption has no documented SourceArn context.
    # Unsupported condition keys would prevent assumption; trust is service-specific.
    return doc([{'Effect':'Allow','Principal':{'Service':service},'Action':'sts:AssumeRole'}])


def base(description):
    return {'AWSTemplateFormatVersion':'2010-09-09','Description':description,
            'Metadata':{'ProjectCodeVersion':(Path(__file__).resolve().parents[1]/'VERSION').read_text().strip(),
                        'AWSToolsMetrics':{'AWSAgentToolkit':'aws-cloudformation@3'},
                        'com.aws.cloudformation.Context':{'ref':['../README.md','../SECURITY.md'],
                            'must':['Five independent accounts; 14 private EC2 nodes; three physical AZ IDs.',
                                    'No local VM operations. No secrets or CA private key in templates.']}},
            'Parameters':{},'Resources':{},'Outputs':{}}


def resource(t, name, kind, properties, why, must=(), **kw):
    t['Resources'][name] = {'Type':kind,'Metadata':{'com.aws.cloudformation.Context':
                           {'why':why,'must':list(must)}},'Properties':properties,**kw}


def output(t, name, value, description):
    t['Outputs'][name] = {'Value':value,'Description':description}


def tags(c, node='shared', role='infrastructure'):
    return [{'Key':k,'Value':v} for k,v in {'Project':c['project'],'Environment':c['environment'],
                                         'Node':node,'Role':role}.items()]


def param(t, name, pattern=None, kind='String', **kw):
    t['Parameters'][name]={'Type':kind,**({'AllowedPattern':pattern} if pattern else {}),**kw}


def bootstrap(c, a):
    t=base('Administrator bootstrap: scoped Mac operations, CloudFormation service role, per-node EC2 roles and peering trust.')
    pre=prefix(c); account=a['account_id']; region=c['region']
    ec2=f'arn:aws:ec2:{region}:{account}:'
    cf=f'arn:aws:cloudformation:{region}:{account}:'
    iam=f'arn:aws:iam::{account}:role/'
    exec_name=pre+'-cfn-execution'
    accepter_name=pre+'-peering-accepter'
    runtime_arns=[iam+role_name(c,n['name']) for n in a['nodes']]
    # No IAM write permissions: all runtime roles are created by this admin stack.
    ec2_types=('vpc','subnet','route-table','internet-gateway','natgateway','elastic-ip',
               'security-group','security-group-rule','network-interface','vpc-endpoint',
               'vpc-peering-connection','instance','volume')
    ec2_writes=['CreateVpc','DeleteVpc','ModifyVpcAttribute','CreateSubnet','DeleteSubnet',
       'ModifySubnetAttribute','CreateRouteTable','DeleteRouteTable','AssociateRouteTable',
       'DisassociateRouteTable','CreateRoute','DeleteRoute','ReplaceRoute','CreateInternetGateway',
       'AttachInternetGateway','DetachInternetGateway','DeleteInternetGateway','AllocateAddress',
       'ReleaseAddress','CreateNatGateway','DeleteNatGateway','CreateSecurityGroup','DeleteSecurityGroup',
       'AuthorizeSecurityGroupIngress','RevokeSecurityGroupIngress','AuthorizeSecurityGroupEgress',
       'RevokeSecurityGroupEgress','CreateNetworkInterface','DeleteNetworkInterface',
       'ModifyNetworkInterfaceAttribute','CreateVpcEndpoint','DeleteVpcEndpoints','ModifyVpcEndpoint',
       'CreateVpcPeeringConnection','DeleteVpcPeeringConnection','ModifyVpcPeeringConnectionOptions','ReplaceRouteTableAssociation','CreateTags','DeleteTags',
       'TerminateInstances','ModifyInstanceAttribute','AssociateIamInstanceProfile',
       'ModifyInstanceMetadataOptions','ModifyPrivateDnsNameOptions']
    read=['DescribeVpcs','DescribeVpcAttribute','DescribeSubnets','DescribeRouteTables',
       'DescribeInternetGateways','DescribeAddresses','DescribeNatGateways','DescribeSecurityGroups',
       'DescribeSecurityGroupRules','DescribeNetworkInterfaces','DescribeVpcEndpoints',
       'DescribeVpcPeeringConnections','DescribeInstances','DescribeInstanceAttribute',
       'DescribeInstanceStatus','DescribeVolumes','DescribeImages','DescribeTags',
       'DescribeInstanceCreditSpecifications','DescribeLaunchTemplates','DescribeLaunchTemplateVersions',
       'DescribeIamInstanceProfileAssociations','DescribeKeyPairs','DescribeNetworkAcls','DescribeVpnGateways',
       'DescribeAvailabilityZones','DescribeInstanceTypes','DescribeInstanceTypeOfferings']
    buckets=[artifact_bucket(c,a)] + ([checkpoint_bucket(c)] if a['profile']=='encore1' else [])
    bucket_arns=['arn:aws:s3:::'+b for b in buckets]
    exec_policy=doc([
       allow(['ec2:'+x for x in read],'*',Condition={'StringEquals':{'aws:RequestedRegion':region}}),
       allow(['ec2:'+x for x in ec2_writes],[ec2+x+'/*' for x in ec2_types]),
       allow(['ec2:RunInstances'],[ec2+x+'/*' for x in ('instance','volume','subnet','network-interface','security-group')]
             +[f'arn:aws:ec2:{region}::image/*',f'arn:aws:ec2:{region}::snapshot/*']),
       allow('ec2:ModifyInstanceCreditSpecification',ec2+'instance/*',
             Condition={'StringEquals':{'ec2:ResourceTag/Project':c['project'],
                                       'ec2:ResourceTag/Environment':c['environment']}}),
       allow(['iam:PassRole'],runtime_arns,Condition={'StringEquals':{'iam:PassedToService':'ec2.amazonaws.com'}}),
       allow(['iam:GetRole'],runtime_arns),
       allow(['ssm:DescribeAssociation','ssm:ListAssociations'],'*',Condition={'StringEquals':{'aws:RequestedRegion':region}}),
       allow(['iam:GetInstanceProfile'],[f'arn:aws:iam::{account}:instance-profile/'+role_name(c,n['name']) for n in a['nodes']]),
       allow(['sts:AssumeRole'],[f'arn:aws:iam::{account_ids(c)[y]}:role/{accepter_name}' for x,y in c['peering_pairs'] if x==a['profile']])
           if any(x==a['profile'] for x,y in c['peering_pairs']) else allow('sts:GetCallerIdentity','*'),
       allow(['s3:CreateBucket','s3:DeleteBucket','s3:GetBucketLocation','s3:GetBucketPolicy','s3:PutBucketPolicy',
              's3:DeleteBucketPolicy','s3:GetBucketPublicAccessBlock','s3:PutBucketPublicAccessBlock',
              's3:GetEncryptionConfiguration','s3:PutEncryptionConfiguration','s3:GetBucketVersioning',
              's3:PutBucketVersioning','s3:GetBucketTagging','s3:PutBucketTagging','s3:GetBucketOwnershipControls',
              's3:PutBucketOwnershipControls','s3:GetLifecycleConfiguration','s3:PutLifecycleConfiguration',
              's3:GetAccelerateConfiguration','s3:GetAnalyticsConfiguration','s3:GetBucketCORS',
              's3:GetInventoryConfiguration','s3:GetBucketLogging','s3:GetMetricsConfiguration',
              's3:GetBucketNotification','s3:GetReplicationConfiguration','s3:GetBucketWebsite',
              's3:GetBucketObjectLockConfiguration','s3:GetBucketAbac','s3:GetIntelligentTieringConfiguration',
              's3:GetBucketMetadataTableConfiguration','s3:ListBucket','s3:ListTagsForResource'],bucket_arns),
    ])
    exec_policy['Statement']=[s for s in exec_policy['Statement'] if s['Action']!='sts:GetCallerIdentity']
    peer_sources=[account_ids(c)[x] for x,y in c['peering_pairs'] if y==a['profile']]
    if peer_sources:
        exec_policy['Statement'].append(allow(['iam:GetRole','iam:GetRolePolicy','iam:PutRolePolicy','iam:DeleteRolePolicy'],
            iam+accepter_name))
    if a['profile']=='encore1':
        lb=f'arn:aws:elasticloadbalancing:{region}:{account}:'
        exec_policy['Statement'] += [
            allow('ec2:DescribeAccountAttributes','*',
                Condition={'StringEquals':{'aws:RequestedRegion':region}}),
            allow(['elasticloadbalancing:'+x for x in ('DescribeLoadBalancers','DescribeLoadBalancerAttributes',
                'DescribeTargetGroups','DescribeTargetGroupAttributes','DescribeListeners','DescribeTags','DescribeTargetHealth')],'*'),
            allow(['elasticloadbalancing:'+x for x in ('CreateLoadBalancer','DeleteLoadBalancer','ModifyLoadBalancerAttributes',
                'CreateTargetGroup','DeleteTargetGroup','ModifyTargetGroup','ModifyTargetGroupAttributes','CreateListener',
                'DeleteListener','ModifyListener','AddListenerCertificates','RemoveListenerCertificates','AddTags','RemoveTags',
                'RegisterTargets','DeregisterTargets')],
                [lb+'loadbalancer/app/'+pre+'-web/*',lb+'targetgroup/'+pre+'-web/*',
                 lb+'listener/app/'+pre+'-web/*/*',lb+'listener-rule/app/'+pre+'-web/*/*/*']),
            allow('iam:CreateServiceLinkedRole',f'arn:aws:iam::{account}:role/aws-service-role/elasticloadbalancing.amazonaws.com/AWSServiceRoleForElasticLoadBalancing',
                Condition={'StringEquals':{'iam:AWSServiceName':'elasticloadbalancing.amazonaws.com'}}),
        ]
    resource(t,'ExecutionRole','AWS::IAM::Role',{'RoleName':exec_name,
       'AssumeRolePolicyDocument':trust('cloudformation.amazonaws.com'),
       'Policies':[{'PolicyName':'project-resources','PolicyDocument':exec_policy}],'Tags':tags(c)},
       'CloudFormation owns infrastructure; ordinary IAM role/trust/boundary creation remains administrator-only.',
       ['PassRole only the named EC2 runtime roles; regional EC2 resource wildcards require review.',
        'CPU-credit modification requires this project and environment on the target instance.',
        'Only the boundary-constrained peering role inline policy may be changed by network stacks.',
        'The sole service-linked-role exception is the AWS-managed ELB service role.'])
    # Accepter role only needed in requester->accepter targets. Bootstrap establishes trust;
    # a separate admin stack binds accept permissions to the actual created VPC ID.
    if peer_sources:
        resource(t,'PeeringBoundary','AWS::IAM::ManagedPolicy',{
            'ManagedPolicyName':pre+'-peering-boundary',
            'PolicyDocument':doc([
                allow('ec2:AcceptVpcPeeringConnection',ec2+'vpc/*',
                    Condition={'StringEquals':{'ec2:ResourceTag/Project':c['project'],'ec2:ResourceTag/Environment':c['environment']}}),
                allow('ec2:AcceptVpcPeeringConnection',ec2+'vpc-peering-connection/*',
                    Condition={'ArnLike':{'ec2:AccepterVpc':ec2+'vpc/*'}}),
            ])},'Caps the accepter role at acceptance of project-tagged VPCs; inline policies cannot expand beyond this boundary.',
            ['CF execution cannot change/remove this boundary or edit accepter trust.',
             'Accept requires both VPC and peering-connection authorization; tags are checked on the VPC.'])
        resource(t,'PeeringAccepter','AWS::IAM::Role',{'RoleName':accepter_name,
          'PermissionsBoundary':ref('PeeringBoundary'),
          'AssumeRolePolicyDocument':doc([{'Effect':'Allow','Principal':{'AWS':[f'arn:aws:iam::{x}:root' for x in peer_sources]},
              'Action':'sts:AssumeRole','Condition':{'ArnEquals':{'aws:PrincipalArn':[f'arn:aws:iam::{x}:role/{exec_name}' for x in peer_sources]}}}]),
          'Tags':tags(c)},'Cross-account peering acceptance by requester CloudFormation roles only.',
          ['No operator/user/root session trust; network stacks bind acceptance to their actual VPC ID.',
           'Keep the administrator-owned permissions boundary attached.'])
        output(t,'PeeringAccepterArn',attr('PeeringAccepter'),'Accepter role; initially no acceptance policy')
    for n in a['nodes']:
        lid=logical(n['name']); bucket=artifact_bucket(c,a)
        policies=[allow('s3:GetBucketLocation','arn:aws:s3:::'+bucket),
            allow('s3:ListBucket','arn:aws:s3:::'+bucket,Condition={'StringLike':{'s3:prefix':['public/*',f'private/{n["name"]}/*']}}),
            allow('s3:GetObject',[f'arn:aws:s3:::{bucket}/public/*',f'arn:aws:s3:::{bucket}/private/{n["name"]}/*'])]
        if n['role'] in ('control','spark'):
            b='arn:aws:s3:::'+checkpoint_bucket(c)
            path=f"aws/{c['environment']}/*"
            policies += [allow('s3:GetBucketLocation',b),allow('s3:ListBucket',b,Condition={'StringLike':{'s3:prefix':path}}),
                allow(['s3:GetObject','s3:PutObject','s3:DeleteObject','s3:AbortMultipartUpload','s3:ListMultipartUploadParts'],b+'/'+path)]
        resource(t,lid+'Role','AWS::IAM::Role',{'RoleName':role_name(c,n['name']),
            'AssumeRolePolicyDocument':trust('ec2.amazonaws.com'),
            'ManagedPolicyArns':['arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'],
            'Policies':[{'PolicyName':'node-storage','PolicyDocument':doc(policies)}],'Tags':tags(c,n['name'],n['role'])},
            'SSM-managed EC2 with its own private artifact path; Spark and Control use checkpoint S3.',
            ['No AWS keys in code; no CA private key in artifact; no fencing permission until HA implementation review.'])
        resource(t,lid+'Profile','AWS::IAM::InstanceProfile',{'InstanceProfileName':role_name(c,n['name']),
            'Roles':[ref(lid+'Role')]},'Separate named instance profile for this logical node.')
        output(t,lid+'InstanceProfile',ref(lid+'Profile'),'Instance profile name')
    operator_actions=['DescribeChangeSet','DeleteChangeSet','ExecuteChangeSet',
        'DescribeStacks','DescribeStackResources','ListStackResources','DeleteStack','GetTemplate',
        'DescribeStackEvents','DescribeEvents','ListChangeSets']
    operator=doc([
        allow(['cloudformation:'+x for x in operator_actions],
              [cf+f'stack/{pre}-{a["profile"]}-*/*']),
        allow('cloudformation:CreateChangeSet',cf+f'stack/{pre}-{a["profile"]}-*/*',
              Condition={'ArnEquals':{'cloudformation:RoleArn':iam+exec_name}}),
        allow(['cloudformation:ListStacks','cloudformation:ValidateTemplate','cloudformation:GetTemplateSummary'],'*'),
        allow('iam:PassRole',iam+exec_name,Condition={'StringEquals':{'iam:PassedToService':'cloudformation.amazonaws.com'}}),
        allow(['ec2:'+x for x in read],'*',Condition={'StringEquals':{'aws:RequestedRegion':region}}),
        allow(['ssm:DescribeInstanceInformation','ssm:GetCommandInvocation','ssm:ListCommands','ssm:ListCommandInvocations'],'*',
              Condition={'StringEquals':{'aws:RequestedRegion':region}}),
        allow('ssm:SendCommand',f'arn:aws:ec2:{region}:{account}:instance/*',
              Condition={'StringEquals':{'ssm:resourceTag/Project':c['project'],'ssm:resourceTag/Environment':c['environment']}}),
        allow('ssm:SendCommand',[f'arn:aws:ssm:{region}::document/AWS-RunShellScript',f'arn:aws:ssm:{region}::document/AWS-RunRemoteScript']),
        allow('servicequotas:GetServiceQuota',f'arn:aws:servicequotas:{region}:{account}:ec2/L-1216C47A'),
        allow(['s3:ListBucket','s3:GetBucketLocation'],bucket_arns),
        allow(['s3:PutObject','s3:GetObject'],f'arn:aws:s3:::{artifact_bucket(c,a)}/*'),
        allow(['s3:GetBucketTagging','s3:ListBucketVersions','s3:ListBucketMultipartUploads','s3:DeleteBucket'],bucket_arns),
        allow(['s3:DeleteObject','s3:DeleteObjectVersion','s3:AbortMultipartUpload'],[b+'/*' for b in bucket_arns]),
    ])
    if a['profile']=='encore1':
        operator['Statement'].append(allow(['elasticloadbalancing:DescribeLoadBalancers','elasticloadbalancing:DescribeTargetGroups',
            'elasticloadbalancing:DescribeTargetHealth','elasticloadbalancing:DescribeTags'],'*'))
        operator['Statement'].append(allow('acm:DescribeCertificate',f'arn:aws:acm:{region}:{account}:certificate/*'))
    # DescribeEvents is denied by the live service with stack/change-set ARNs,
    # despite the SAR listing those resources. This exception is read-only and
    # regional; all mutation and IAM permissions keep their existing scope.
    operator['Statement'].append(allow('cloudformation:DescribeEvents','*',
        Condition={'StringEquals':{'aws:RequestedRegion':region}}))
    if a['profile']=='encore1':
        resource(t,'OperatorRole','AWS::IAM::Role',{'RoleName':pre+'-operator',
            'AssumeRolePolicyDocument':doc([{'Effect':'Allow','Principal':{'AWS':c['operator_principal_arn']},
                'Action':'sts:AssumeRole','Condition':{'Null':{'aws:SignInSessionArn':'false'}}}]),
            'Policies':[{'PolicyName':'project-operations','PolicyDocument':operator}],'Tags':tags(c)},
            'Scoped operator from encore1 login; regional validation-event reads; student remains bootstrap administrator.',
            ['SignInSessionArn is session context presence, not a direct MFA proof.'])
        output(t,'OperatorRoleArn',attr('OperatorRole'),'Scoped operator role for encore1')
    else:
        resource(t,'OperatorPolicy','AWS::IAM::ManagedPolicy',{'ManagedPolicyName':pre+'-operator',
           'Roles':['ProjectInfraRole'],'PolicyDocument':operator},
           'Project CloudFormation/SSM operations and regional validation-event reads on the existing team role.',
           ['Administrator applies; preserves existing role trust and EC2 managed policies.'])
    output(t,'ExecutionRoleArn',attr('ExecutionRole'),'Role passed to subsequent infrastructure change sets')
    return t


def acceptor(c,a):
    t=base('Administrator binds peering acceptance to one actual project VPC; requester trust lives in bootstrap.')
    param(t,'VpcId',r'vpc-[0-9a-f]+')
    vpc=sub('arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:vpc/${VpcId}')
    policy=doc([allow('ec2:AcceptVpcPeeringConnection',vpc),
        allow('ec2:AcceptVpcPeeringConnection',sub('arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:vpc-peering-connection/*'),
              Condition={'StringEquals':{'ec2:AccepterVpc':vpc}})])
    resource(t,'AccepterPolicy','AWS::IAM::Policy',{'PolicyName':prefix(c)+'-accept-project-vpc',
        'Roles':[prefix(c)+'-peering-accepter'],'PolicyDocument':policy},
        'Limits both required acceptance resources to the actual created VPC.',
        ['Apply with account admin after network stack; operator cannot grant this to itself.'])
    return t


def ingress_sources(c,node):
    nodes=[n for a in c['accounts'] for n in a['nodes']]
    role=node['role']; rules=[]
    def add(roles,ports):
        for p in nodes:
            if p['role'] in roles:
                for start,end in ports:
                    rules.append({'IpProtocol':'tcp','FromPort':start,'ToPort':end,'CidrIp':p['private_ip']+'/32'})
    if role=='kafka':
        add(('kafka','spark','control'),[(9092,9092)]); add(('kafka',),[(9093,9093)])
    elif role=='spark':
        add(('spark','control'),[(2281,2281),(7077,7078),(8080,8080),(39000,39032),(39050,39082),(39100,39132)])
        add(('spark',),[(2888,2888),(3888,3888)])
    elif role=='control':
        add(('spark','control'),[(39000,39032),(39050,39082),(39100,39132)])
    elif role=='es':
        add(('spark','control','es'),[(9200,9200)]); add(('es',),[(9300,9300)])
    elif role in ('postgresql','mongodb') and c['service_ports'].get(role):
        add(('control',) if role=='postgresql' else ('advertising','control'),[(c['service_ports'][role],c['service_ports'][role])])
    return rules


def network(c,a):
    t=base('One private project VPC, three AZ-ID subnet pairs, one zonal NAT, S3 endpoint and stable per-node ENIs.')
    for z in 'abc': param(t,'Az'+z.upper(),r'apne2-az[1-4]')
    common=tags(c)
    resource(t,'Vpc','AWS::EC2::VPC',{'CidrBlock':a['cidr'],'EnableDnsSupport':True,'EnableDnsHostnames':True,'Tags':common},
        'Independent non-overlapping account VPC.', ['Review connected local/VPN CIDRs before apply.'])
    if any(y==a['profile'] for x,y in c['peering_pairs']):
        vpc=sub('arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:vpc/${Vpc}')
        resource(t,'AccepterPolicy','AWS::IAM::Policy',{'PolicyName':prefix(c)+'-accept-project-vpc',
            'Roles':[prefix(c)+'-peering-accepter'],'PolicyDocument':doc([
                allow('ec2:AcceptVpcPeeringConnection',vpc),
                allow('ec2:AcceptVpcPeeringConnection',sub('arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:vpc-peering-connection/*'),
                    Condition={'ArnEquals':{'ec2:AccepterVpc':vpc}})])},
            'Binds the current VPC inside the network stack, so every create/delete cycle needs no account-owner intervention.',
            ['The accepter permissions boundary and trust are administrator-owned.',
             'Remove peer stacks before deleting this network-owned policy.'])
    resource(t,'InternetGateway','AWS::EC2::InternetGateway',{'Tags':common},'Outbound Internet via project NAT and future public ALB.')
    resource(t,'GatewayAttachment','AWS::EC2::VPCGatewayAttachment',{'VpcId':ref('Vpc'),'InternetGatewayId':ref('InternetGateway')},'Attach only to the project VPC.')
    resource(t,'PublicRoutes','AWS::EC2::RouteTable',{'VpcId':ref('Vpc'),'Tags':common},'Public subnet routing for NAT and ALB.')
    resource(t,'PublicDefault','AWS::EC2::Route',{'RouteTableId':ref('PublicRoutes'),'DestinationCidrBlock':'0.0.0.0/0','GatewayId':ref('InternetGateway')},'Internet egress route.',DependsOn='GatewayAttachment')
    for z in 'abc':
        Z=z.upper()
        for kind,private in (('Public',False),('Private',True)):
            resource(t,kind+Z,'AWS::EC2::Subnet',{'VpcId':ref('Vpc'),'AvailabilityZoneId':ref('Az'+Z),
                'CidrBlock':subnet_cidr(a,z,private),'MapPublicIpOnLaunch':False,'Tags':common},
                'Subnet placement by physical AZ ID across accounts.', ['Never replace AZ ID by an assumed account-local AZ name.'])
        resource(t,'PrivateRoutes'+Z,'AWS::EC2::RouteTable',{'VpcId':ref('Vpc'),'Tags':common},'Private routes: local, NAT and direct peering only.')
        for kind,rt in (('Public','PublicRoutes'),('Private','PrivateRoutes'+Z)):
            resource(t,kind+'Association'+Z,'AWS::EC2::SubnetRouteTableAssociation',
                {'SubnetId':ref(kind+Z),'RouteTableId':ref(rt)},'Attach the correct route table.')
        output(t,'PrivateSubnet'+Z,ref('Private'+Z),'Private subnet ID')
        output(t,'PublicSubnet'+Z,ref('Public'+Z),'Public subnet ID')
        output(t,'PrivateRouteTable'+Z,ref('PrivateRoutes'+Z),'Private route table ID')
    resource(t,'NatAddress','AWS::EC2::EIP',{'Domain':'vpc','Tags':common},'One paid NAT IPv4 per VPC.',DependsOn='GatewayAttachment')
    resource(t,'Nat','AWS::EC2::NatGateway',{'AllocationId':attr('NatAddress','AllocationId'),
        'SubnetId':ref('Public'+a['nat_slot'].upper()),'Tags':common},'Approved one-zonal-NAT-per-VPC cost compromise.',
        ['All private AZs share this NAT; NAT AZ failure interrupts external connectivity.'])
    for z in 'ABC':
        resource(t,'PrivateDefault'+z,'AWS::EC2::Route',{'RouteTableId':ref('PrivateRoutes'+z),
            'DestinationCidrBlock':'0.0.0.0/0','NatGatewayId':ref('Nat')},'Internet route; private cluster traffic uses direct peering.')
    resource(t,'S3Endpoint','AWS::EC2::VPCEndpoint',{'VpcId':ref('Vpc'),'VpcEndpointType':'Gateway',
        'ServiceName':sub('com.amazonaws.${AWS::Region}.s3'),'RouteTableIds':[ref('PrivateRoutes'+z) for z in 'ABC']},
        'Each VPC gets its own S3 gateway endpoint; endpoint cannot be shared through peering.')
    if a['profile']=='encore1':
        resource(t,'AlbSG','AWS::EC2::SecurityGroup',{'VpcId':ref('Vpc'),'GroupDescription':'Private target reference; listener ingress added by later ALB stack','Tags':common},
            'Dedicated ALB SG, attached only to the ALB; no inbound rule until protocol and restricted client CIDR are selected.')
        output(t,'AlbSecurityGroupId',ref('AlbSG'),'Future ALB SG')
    for n in a['nodes']:
        lid=logical(n['name']); rules=ingress_sources(c,n)
        if n['role']=='control' and web_port(c):
            rules.append({'IpProtocol':'tcp','FromPort':web_port(c),
                          'ToPort':web_port(c),'SourceSecurityGroupId':ref('AlbSG')})
        resource(t,lid+'SG','AWS::EC2::SecurityGroup',{'VpcId':ref('Vpc'),'GroupDescription':'Project private '+n['role'],
            'SecurityGroupIngress':rules,'Tags':tags(c,n['name'],n['role'])},
            'Exact node /32 sources and service ports derived from pinned Ubuntu renderer.',
            ['No public SSH/DB/Kibana/Spark UI; Spark maxRetries=32 is included.'] +
            (['MongoDB27017 admits only advertising and the two Control /32 addresses; weather uses a separate database/user.',
              'Spark executors remain excluded; no transitive peering or additional peering is assumed.'] if n['role']=='mongodb' else []))
        resource(t,lid+'ENI','AWS::EC2::NetworkInterface',{'SubnetId':ref('Private'+n['az_slot'].upper()),
            'PrivateIpAddress':n['private_ip'],'GroupSet':[ref(lid+'SG')],'Tags':tags(c,n['name'],n['role'])},
            'Network stack owns stable node primary ENI separately from compute stack.',
            ['Delete old compute and wait for ENI available before reusing; no create-before-delete compute replacement.'])
        output(t,lid+'EniId',ref(lid+'ENI'),'Stable primary ENI ID')
    output(t,'VpcId',ref('Vpc'),'Project VPC ID')
    return t


def storage(c,a):
    t=base('Private encrypted versioned install artifacts and optional cross-account Spark checkpoint bucket; retained by default.')
    entries=[('Artifacts',artifact_bucket(c,a))]+([('Checkpoints',checkpoint_bucket(c))] if a['profile']=='encore1' else [])
    for lid,bucket in entries:
        resource(t,lid,'AWS::S3::Bucket',{'BucketName':bucket,
            'PublicAccessBlockConfiguration':{k:True for k in ('BlockPublicAcls','BlockPublicPolicy','IgnorePublicAcls','RestrictPublicBuckets')},
            'BucketEncryption':{'ServerSideEncryptionConfiguration':[{'ServerSideEncryptionByDefault':{'SSEAlgorithm':'AES256'}}]},
            'VersioningConfiguration':{'Status':'Enabled'},'OwnershipControls':{'Rules':[{'ObjectOwnership':'BucketOwnerEnforced'}]},
            'Tags':tags(c)},'Environment-owned S3 storage separated from original music source backups.',
            ['Retained until explicit version-aware purge; active checkpoints have no expiry.'],
            DeletionPolicy='Retain',UpdateReplacePolicy='Retain')
        arn='arn:aws:s3:::'+bucket
        statements=[{'Effect':'Deny','Principal':'*','Action':'s3:*','Resource':[arn,arn+'/*'],
                     'Condition':{'Bool':{'aws:SecureTransport':'false'}}}]
        if lid=='Checkpoints':
            principals=[f'arn:aws:iam::{acc["account_id"]}:role/{role_name(c,n["name"])}'
                        for acc in c['accounts'] for n in acc['nodes'] if n['role'] in ('control','spark')]
            path=f"aws/{c['environment']}/*"
            statements += [allow('s3:GetBucketLocation',arn,Principal={'AWS':principals}),
                allow('s3:ListBucket',arn,Principal={'AWS':principals},Condition={'StringLike':{'s3:prefix':path}}),
                allow(['s3:GetObject','s3:PutObject','s3:DeleteObject','s3:AbortMultipartUpload','s3:ListMultipartUploadParts'],
                      arn+'/'+path,Principal={'AWS':principals})]
        resource(t,lid+'Policy','AWS::S3::BucketPolicy',{'Bucket':ref(lid),'PolicyDocument':doc(statements)},
            'Deny non-TLS access; checkpoint allowlist matches exact Control and Spark roles.',
            ['All five bootstrap stacks must exist before checkpoint policy references their role principals.'])
        output(t,lid+'Bucket',ref(lid),'Owned bucket; deletion retains object versions')
    return t


def peering(c):
    t=base('One direct cross-account VPC peering connection; route stacks are owned independently by both accounts.')
    for k,pattern in [('VpcId','vpc-[0-9a-f]+'),('PeerVpcId','vpc-[0-9a-f]+'),('PeerOwnerId','[0-9]{12}'),
                      ('PeerRoleArn',r'arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9-]+')]:param(t,k,pattern)
    resource(t,'Peer','AWS::EC2::VPCPeeringConnection',{'VpcId':ref('VpcId'),'PeerVpcId':ref('PeerVpcId'),
        'PeerOwnerId':ref('PeerOwnerId'),'PeerRoleArn':ref('PeerRoleArn'),'AssumeRoleRegion':c['region'],'Tags':tags(c)},
        'Direct peering: no transit via encore1 and no shared NAT.', ['CIDRs must not overlap.'])
    output(t,'PeeringId',ref('Peer'),'Direct peering ID for route stacks')
    return t


def route(c):
    t=base('One remote VPC CIDR route in each private AZ route table; explicit account-to-account output parameters.')
    param(t,'PeeringId','pcx-[0-9a-f]+');param(t,'DestinationCidr',r'[0-9.]+/[0-9]+')
    for z in 'ABC':
        param(t,'RouteTable'+z,'rtb-[0-9a-f]+')
        resource(t,'Route'+z,'AWS::EC2::Route',{'RouteTableId':ref('RouteTable'+z),
           'DestinationCidrBlock':ref('DestinationCidr'),'VpcPeeringConnectionId':ref('PeeringId')},
           'Owned in this account; reciprocal routes must also exist.')
    return t


def compute(c,a,n):
    t=base('Single private Ubuntu EC2 attached to a stable separately-owned ENI; remove then recreate for replacement.')
    for k,pattern in [('AmiId','ami-[0-9a-f]+'),('InstanceType',r'[a-z0-9]+\.[a-z0-9]+'),
                      ('EniId','eni-[0-9a-f]+')]: param(t,k,None if k=='AmiId' else pattern,kind='AWS::EC2::Image::Id' if k=='AmiId' else 'String')
    for k in ('RootGiB','DataGiB'):param(t,k,kind='Number',MinValue=8,MaxValue=16384)
    if n.get('instance_type'):
        t['Parameters']['InstanceType']['AllowedValues']=[n['instance_type']]
    userdata='''#!/bin/bash
set -Eeuo pipefail
hostnamectl set-hostname NODE_NAME
printf 'preserve_hostname: true\n' > /etc/cloud/cloud.cfg.d/99-music-hostname.cfg
if snap list amazon-ssm-agent >/dev/null 2>&1; then
  snap start amazon-ssm-agent
else
  snap install amazon-ssm-agent --classic
  snap start amazon-ssm-agent
fi
'''.replace('NODE_NAME',n['name'])
    resource(t,'Instance','AWS::EC2::Instance',{'ImageId':ref('AmiId'),'InstanceType':ref('InstanceType'),
       'IamInstanceProfile':role_name(c,n['name']),
       'NetworkInterfaces':[{'NetworkInterfaceId':ref('EniId'),'DeviceIndex':'0'}],
       'MetadataOptions':{'HttpTokens':'required','HttpEndpoint':'enabled','HttpPutResponseHopLimit':1,'InstanceMetadataTags':'enabled'},
       'BlockDeviceMappings':[{'DeviceName':'/dev/sda1','Ebs':{'Encrypted':True,'VolumeType':'gp3','VolumeSize':ref('RootGiB'),'DeleteOnTermination':True}},
                              {'DeviceName':'/dev/sdf','Ebs':{'Encrypted':True,'VolumeType':'gp3','VolumeSize':ref('DataGiB'),'DeleteOnTermination':True}}],
       'PropagateTagsToVolumeOnCreation':True,
       'UserData':{'Fn::Base64':userdata},'Tags':tags(c,n['name'],n['role'])},
       'Only EC2 ownership changes on node replacement; data reset is explicitly allowed for new generations.',
       ['Never add DeleteOnTermination to an existing ENI launch specification.',
        'Data disk formatting requires explicit init-disk stage; cloud-init does not format it.',
        'Changing AMI/type/volume through ordinary replacement may collide with attached primary ENI.'])
    if (n.get('instance_type') or '').startswith('t3.'):
        if n.get('credit_mode') != 'standard':
            raise ValueError('Selected T3 budget requires explicit standard credit mode: '+n['name'])
        t['Resources']['Instance']['Properties']['CreditSpecification']={'CPUCredits':'standard'}
        context=t['Resources']['Instance']['Metadata']['com.aws.cloudformation.Context']
        context['why']+=' T3 Standard avoids surplus CPU-credit charges in the selected 96h estimate.'
        context['must'].append('Keep Standard CPU credits for the selected budget; credit exhaustion reduces CPU to baseline.')
    output(t,'InstanceId',ref('Instance'),'Actual EC2 ID; do not infer it from logical name')
    output(t,'PrivateIp',attr('Instance','PrivateIp'),'Actual private IP to verify against ENI inventory')
    return t


def alb(c):
    t=base('Restricted ALB and two Control targets; explicit temporary HTTP on default DNS, ACM HTTPS after domain selection.')
    for k in ('VpcId','PublicSubnetA','PublicSubnetB','SecurityGroupId','ControlAId','ControlBId','ClientCidr','HealthPath'):
        param(t,k)
    param(t,'ClientCidr',pattern=r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}/(?:[1-9]|[12][0-9]|3[0-2])')
    param(t,'Protocol',Default='HTTPS',AllowedValues=['HTTP','HTTPS'])
    param(t,'CertificateArn',Default='')
    param(t,'TargetPort',kind='Number',MinValue=1,MaxValue=65535)
    t['Conditions']={'UseHttps':{'Fn::Equals':[ref('Protocol'),'HTTPS']}}
    t['Rules']={'HttpsNeedsCertificate':{'Assertions':[{'Assert':{'Fn::Or':[
        {'Fn::Equals':[ref('Protocol'),'HTTP']},{'Fn::Not':[{'Fn::Equals':[ref('CertificateArn'),'']}]}]},
        'AssertDescription':'HTTPS requires a certificate from encore1 in Seoul.'}]}}
    conditional=lambda yes,no:{'Fn::If':['UseHttps',yes,no]}
    port=conditional(443,80)
    name=prefix(c)+'-web'
    if len(name)>32:raise ValueError('ALB name exceeds 32 characters')
    resource(t,'Ingress','AWS::EC2::SecurityGroupIngress',{'GroupId':ref('SecurityGroupId'),
        'IpProtocol':'tcp','FromPort':port,'ToPort':port,'CidrIp':ref('ClientCidr')},
        'Selected HTTP/HTTPS port is restricted on the dedicated ALB SG; changing port replaces only this ingress rule.',
        ['Never use an unrestricted client CIDR.','HTTP is an explicit temporary choice; use ACM HTTPS with an owned domain later.'])
    resource(t,'LoadBalancer','AWS::ElasticLoadBalancingV2::LoadBalancer',{'Name':name,'Type':'application',
        'Scheme':'internet-facing','IpAddressType':'ipv4','Subnets':[ref('PublicSubnetA'),ref('PublicSubnetB')],
        'SecurityGroups':[ref('SecurityGroupId')],'Tags':tags(c)},'One public entry point in two physical AZs; stable identity during protocol changes.')
    resource(t,'Targets','AWS::ElasticLoadBalancingV2::TargetGroup',{'Name':name,'VpcId':ref('VpcId'),
        'Protocol':'HTTP','Port':ref('TargetPort'),'TargetType':'instance','HealthCheckPath':ref('HealthPath'),
        'Targets':[{'Id':ref('ControlAId')},{'Id':ref('ControlBId')}],'Tags':tags(c)},
        'Traffic targets both Control web applications; ASGI runtime is team-owned and driver leadership remains separate.',
        ['Target health is not proof of Control fencing or application data flow.'])
    resource(t,'Listener','AWS::ElasticLoadBalancingV2::Listener',{'LoadBalancerArn':ref('LoadBalancer'),
        'Port':port,'Protocol':ref('Protocol'),
        'Certificates':conditional([{'CertificateArn':ref('CertificateArn')}],ref('AWS::NoValue')),
        'SslPolicy':conditional('ELBSecurityPolicy-TLS13-1-2-2021-06',ref('AWS::NoValue')),
        'DefaultActions':[{'Type':'forward','TargetGroupArn':ref('Targets')}]},
        'One stable listener: temporary default-DNS HTTP can be updated to ACM HTTPS; no EC2 or data replacement.',
        ['HTTPS requests must use a domain covered by the certificate; the AWS-owned default DNS cannot have our ACM public certificate.'])
    output(t,'LoadBalancerArn',ref('LoadBalancer'),'Owned ALB ARN')
    output(t,'DnsName',attr('LoadBalancer','DNSName'),'ALB DNS name')
    output(t,'DefaultDnsUrl',{'Fn::Join':['',[conditional('https://','http://'),attr('LoadBalancer','DNSName')]]},
        'Use default DNS with HTTP; for HTTPS use your own certificate-covered domain instead.')
    output(t,'TargetGroupArn',ref('Targets'),'Control target group ARN')
    return t


def generate(c,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    templates={}
    for a in c['accounts']:
        for k,fn in [('bootstrap',bootstrap),('network',network),('storage',storage)]:
            templates[stack_name(c,a['profile'],k)]=fn(c,a)
        if any(y==a['profile'] for x,y in c['peering_pairs']):
            templates[stack_name(c,a['profile'],'acceptor')]=acceptor(c,a)
        for n in a['nodes']:
            templates[stack_name(c,a['profile'],'compute-'+n['name'])]=compute(c,a,n)
    templates['peering']=peering(c);templates['route']=route(c)
    templates[stack_name(c,'encore1','alb')]=alb(c)
    for name,t in templates.items():
        root=Path(__file__).resolve().parents[1]
        documents=[root/'README.md',root/'SECURITY.md']
        shared=root.parent/'docs/handoff/infra/README.md'
        if shared.is_file():documents.append(shared)
        t['Metadata']['com.aws.cloudformation.Context']['ref']=[os.path.relpath(p,out.resolve()) for p in documents]
        data=json.dumps(t,indent=2)+'\n'
        if len(data.encode())>51200: raise ValueError('Inline template size limit exceeded: '+name)
        (out/(name+'.json')).write_text(data)
    return templates
