#!/usr/bin/env python3
"""Read-only deployment readiness checks. Never creates AWS resources or change sets."""
import argparse
import concurrent.futures
import copy
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'lib'), str(ROOT / 'bin')]
from awscli import Aws, AwsError
from revision import source_identity
from project import load, blockers, stack_name, prefix, role_name
from templates import bootstrap, logical
from infra import get_stack


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.chmod(0o600)
    temp.replace(path)


def inspect_account(c, a):
    aws = Aws(c, a)
    stack = get_stack(aws, stack_name(c, a['profile'], 'bootstrap'), c)
    if not stack or stack['StackStatus'] not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE'):
        raise ValueError(a['profile'] + ': bootstrap is not complete')
    template = aws.call('cloudformation', 'get-template', '--stack-name', stack['StackId'])['TemplateBody']
    if isinstance(template, str):
        template = json.loads(template)
    expected = bootstrap(c, a)
    mismatches = [k for k, v in expected['Resources'].items()
                  if any(template.get('Resources', {}).get(k, {}).get(field) != v.get(field)
                         for field in ('Type', 'Properties'))]
    resources = aws.call('cloudformation', 'list-stack-resources', '--stack-name', stack['StackId'])['StackResourceSummaries']
    statuses = {r['LogicalResourceId']: r['ResourceStatus'] for r in resources}
    incomplete = [k for k in expected['Resources'] if statuses.get(k) not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE')]
    outputs = {o['OutputKey']: o['OutputValue'] for o in stack.get('Outputs', [])}
    expected_outputs = {logical(n['name']) + 'InstanceProfile': role_name(c, n['name']) for n in a['nodes']}
    arn = 'arn:aws:iam::' + a['account_id'] + ':role/' + prefix(c)
    expected_outputs['ExecutionRoleArn'] = arn + '-cfn-execution'
    expected_outputs['OperatorRoleArn' if a['profile'] == 'encore1' else 'PeeringAccepterArn'] = arn + ('-operator' if a['profile'] == 'encore1' else '-peering-accepter')
    output_match = outputs == expected_outputs
    zones = aws.call('ec2', 'describe-availability-zones')['AvailabilityZones']
    zones = {z['ZoneId']: z['ZoneName'] for z in zones if z['State'] == 'available' and z.get('ZoneType', 'availability-zone') == 'availability-zone'}
    types = sorted({n['instance_type'] for n in a['nodes']})
    descriptions = aws.call('ec2', 'describe-instance-types', '--instance-types', *types)['InstanceTypes']
    sizes = {t['InstanceType']: t for t in descriptions}
    invalid_types = []
    for n in a['nodes']:
        t = sizes.get(n['instance_type'], {})
        if (t.get('Hypervisor') != 'nitro' or t.get('VCpuInfo', {}).get('DefaultVCpus') != n['cpu']
                or t.get('MemoryInfo', {}).get('SizeInMiB') != n['memory_mib']
                or 'x86_64' not in t.get('ProcessorInfo', {}).get('SupportedArchitectures', [])):
            invalid_types.append(n['name'])
    offerings = aws.call('ec2', 'describe-instance-type-offerings', '--location-type', 'availability-zone-id',
                         '--filters', json.dumps([{'Name': 'instance-type', 'Values': types}]))['InstanceTypeOfferings']
    offered = {(o['InstanceType'], o['Location']) for o in offerings}
    quota = aws.call('service-quotas', 'get-service-quota', '--service-code', 'ec2', '--quota-code', 'L-1216C47A')['Quota']['Value']
    vpcs = aws.call('ec2', 'describe-vpcs')['Vpcs']
    cidrs = [v['CidrBlock'] for v in vpcs]
    collisions = [v for v in cidrs if ipaddress.ip_network(v).overlaps(ipaddress.ip_network(a['cidr']))]
    images = aws.call('ec2', 'describe-images', '--owners', '099720109477', '--filters', json.dumps([
        {'Name': 'name', 'Values': ['ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*']},
        {'Name': 'architecture', 'Values': ['x86_64']}, {'Name': 'state', 'Values': ['available']},
        {'Name': 'root-device-type', 'Values': ['ebs']}, {'Name': 'virtualization-type', 'Values': ['hvm']},
    ]))['Images']
    images = [{'id': i['ImageId'], 'name': i['Name'], 'created_at': i['CreationDate']}
              for i in images if i.get('OwnerId') == '099720109477']
    instances = aws.call('ec2', 'describe-instances', '--filters', json.dumps([
        {'Name': 'tag:Project', 'Values': [c['project']]}, {'Name': 'tag:Environment', 'Values': [c['environment']]},
    ]))['Reservations']
    active = [i for r in instances for i in r['Instances'] if i['State']['Name'] != 'terminated']
    ssm = aws.call('ssm', 'describe-instance-information')['InstanceInformationList']
    result = {'profile': a['profile'], 'bootstrap_status': stack['StackStatus'],
              'bootstrap_template_matches': not mismatches, 'different_resources': mismatches,
              'bootstrap_resources_complete': not incomplete, 'incomplete_resources': incomplete,
              'outputs_match': output_match, 'outputs_count': len(outputs),
              'iam_observation': 'CloudFormation deployed properties and completion status; no direct IAM drift check',
              'physical_zones': zones, 'invalid_instance_specs': invalid_types,
              'vcpu_quota': quota, 'required_vcpu': sum(n['cpu'] for n in a['nodes']),
              'vpc_count': len(vpcs), 'existing_vpc_cidrs': cidrs, 'cidr_collisions': collisions,
              'project_ec2_count': len(active), 'ssm_node_count': len(ssm)}
    if a['profile'] == 'encore1':
        result['alb_count'] = len(aws.call('elbv2', 'describe-load-balancers')['LoadBalancers'])
        cert = c['alb'].get('certificate_arn')
        result['certificate_required'] = c['alb'].get('protocol','HTTPS')=='HTTPS'
        result['certificate_issued'] = result['certificate_required'] and bool(cert) and aws.call('acm', 'describe-certificate', '--certificate-arn', cert)['Certificate']['Status'] == 'ISSUED'
    return result, offered, images


def choose_inputs(c, observed):
    common = set.intersection(*(set(r[0]['physical_zones']) for r in observed))
    eligible = []
    for zone in sorted(common):
        if all(all((n['instance_type'], zone) in offers for n in a['nodes'])
               for a, (_, offers, _) in zip(c['accounts'], observed)):
            eligible.append(zone)
    chosen = dict(c['az_ids'])
    if not any(chosen.values()) and len(eligible) >= 3:
        chosen = dict(zip(('a', 'b', 'c'), eligible[:3]))
    image_ids = set.intersection(*({i['id'] for i in r[2]} for r in observed))
    images = [i for i in observed[0][2] if i['id'] in image_ids]
    image = next((i for i in images if i['id'] == c.get('ami_id')), None) if c.get('ami_id') else (max(images, key=lambda i: i['created_at']) if images else None)
    return chosen, image, eligible


def readiness(c, observed, connected_cidrs=()):
    suggested, image, eligible = choose_inputs(c, observed)
    resolved = copy.deepcopy(c)
    resolved['az_ids'] = suggested
    if not resolved.get('ami_id') and image:
        resolved['ami_id'] = image['id']
    networks = [ipaddress.ip_network(a['cidr']) for a in c['accounts']]
    collisions = [str(n) for value in connected_cidrs for n in [ipaddress.ip_network(value)] if any(n.overlaps(v) for v in networks)]
    if connected_cidrs and not collisions and not any(r[0]['cidr_collisions'] for r in observed):
        resolved['network_reviewed'] = True
    issues = []
    for a, (r, offers, images) in zip(c['accounts'], observed):
        for field in ('bootstrap_template_matches', 'bootstrap_resources_complete', 'outputs_match'):
            if not r[field]:
                issues.append(a['profile'] + ': ' + field)
        if r['invalid_instance_specs']:
            issues.append(a['profile'] + ': instance specification mismatch')
        if r['required_vcpu'] > r['vcpu_quota']:
            issues.append(a['profile'] + ': insufficient vCPU quota')
        if r['cidr_collisions']:
            issues.append(a['profile'] + ': VPC CIDR collision')
        for n in a['nodes']:
            if (n['instance_type'], resolved['az_ids'][n['az_slot']]) not in offers:
                issues.append(n['name'] + ': physical AZ/instance type unavailable')
        if resolved['ami_id'] not in {i['id'] for i in images}:
            issues.append(a['profile'] + ': selected AMI is not an available Canonical Ubuntu 24.04 image')
    issues.extend('connected network collision: ' + v for v in collisions)
    # create assigns this ID before its own preflight; no ID is created by this check.
    check_config = copy.deepcopy(resolved)
    check_config['generation'] = check_config.get('generation') or 'automatic-at-create'
    core_inputs = blockers(check_config, 'compute')
    alb_inputs = blockers(check_config, 'alb')
    control=next(r[0] for r in observed if r[0]['profile']=='encore1')
    if resolved['alb'].get('protocol','HTTPS')=='HTTPS' and not control.get('certificate_issued'):
        alb_inputs.append('alb.certificate_arn (ISSUED certificate in encore1/Seoul)')
    client = resolved['alb'].get('allowed_client_cidr')
    if client:
        try:
            network = ipaddress.ip_network(client)
            if network.version != 4 or network.prefixlen == 0:
                alb_inputs.append('alb.allowed_client_cidr must be restricted IPv4')
        except ValueError:
            alb_inputs.append('alb.allowed_client_cidr must be valid IPv4 CIDR')
    return resolved, {'observed_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'read-only; no change sets, stacks, resources, SSM commands or IAM mutations',
        'accounts': [r[0] for r in observed], 'eligible_physical_az_ids': eligible,
        'selected_physical_az_ids': resolved['az_ids'], 'selected_ami': image,
        'alb_protocol': resolved['alb'].get('protocol','HTTPS'), 'alb_endpoint': 'AWS default DNS; own domain required for certificate-valid HTTPS',
        'connected_cidrs_reviewed': list(connected_cidrs), 'issues': sorted(set(issues)),
        'core_missing_inputs': core_inputs, 'alb_missing_inputs': sorted(set(alb_inputs)),
        'core_infrastructure_prerequisites_ready': not issues and not core_inputs,
        'full_infrastructure_prerequisites_ready': not issues and not core_inputs and not alb_inputs,
        'deployment_write_permissions': 'not proven by read-only checks; verify when deployment is authorized',
        'service_predeployment_validation': 'not run; no change sets created',
        'applications': 'Application deployment/integration belongs to the team; infra services and Control lifecycle/fencing are validated separately',
        'resources_created': False, 'implementation': source_identity()}


def scan_accounts(c):
    # All five CLI profiles share encore1 login. Refresh once before fan-out to
    # prevent concurrent CreateOAuth2Token requests against an expired cache.
    Aws(c, next(a for a in c['accounts'] if a['profile']=='encore1'), raw=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        return list(pool.map(lambda a: inspect_account(c, a), c['accounts']))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'config/project.json'))
    parser.add_argument('--out', default=str(ROOT / '.state/preflight/latest.json'))
    parser.add_argument('--without-alb', action='store_true', help='Check only core infrastructure prerequisites; full status is still reported')
    parser.add_argument('--resolve-inputs', action='store_true', help='Update only the ignored local config with discovered AMI/AZ/network review')
    parser.add_argument('--connected-cidr', action='append', default=[])
    args = parser.parse_args()
    source = Path(args.config).resolve()
    if not Path(args.out).resolve().is_relative_to((ROOT / '.state').resolve()):
        raise ValueError('Reports must remain inside the ignored .state directory')
    c = load(source)
    if args.resolve_inputs and source != (ROOT / 'config/project.json').resolve():
        raise ValueError('Input resolution can write only config/project.json')
    observed = scan_accounts(c)
    resolved, report = readiness(c, observed, args.connected_cidr)
    if args.resolve_inputs and not report['issues']:
        write(source, resolved)
    write(args.out, report)
    safe = {k: v for k, v in report.items() if k not in ('accounts', 'selected_ami', 'connected_cidrs_reviewed')}
    safe['accounts'] = [{k: a[k] for k in ('profile', 'bootstrap_status', 'bootstrap_template_matches', 'outputs_match', 'vpc_count', 'project_ec2_count', 'ssm_node_count')} for a in report['accounts']]
    safe['private_report'] = str(Path(args.out))
    print(json.dumps(safe, indent=2))
    ready=report['core_infrastructure_prerequisites_ready' if args.without_alb else 'full_infrastructure_prerequisites_ready']
    return 0 if ready else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, AwsError) as error:
        sys.exit('[FAIL] ' + str(error))
