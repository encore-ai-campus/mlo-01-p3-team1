"""AWS-only topology and deployment input checks. No SDK/credentials dependency."""
import ipaddress
import json
import re
from decimal import Decimal
from pathlib import Path

PROFILES = ('encore1', 'encore2', 'encore3', 'encore4', 'encore5')


def account_ids(c):
    return {a['profile']: a['account_id'] for a in c['accounts']}
PAIRS = {(f'encore{a}', f'encore{b}') for a, b in ((1,2),(1,3),(1,4),(1,5),(2,3),(2,4),(3,4))}
ROLES = {'control': 2, 'postgresql': 1, 'kafka': 3, 'spark': 3, 'es': 3, 'advertising': 1, 'mongodb': 1}
NAME = re.compile(r'[a-z][a-z0-9-]{0,23}\Z')


def web_port(c):
    """Framework-neutral target port; preserve old configs without rewriting them."""
    ports = c['service_ports']
    if 'web' in ports and 'gunicorn' in ports and ports['web'] != ports['gunicorn']:
        raise ValueError('service_ports.web conflicts with legacy service_ports.gunicorn')
    value = ports.get('web', ports.get('gunicorn'))
    if value is not None and (type(value) is not int or not 1 <= value <= 65535):
        raise ValueError('service_ports.web must be an integer in 1..65535')
    return value


def load(path):
    c = json.loads(Path(path).read_text())
    if c['schema_version'] != 1 or c['region'] != 'ap-northeast-2':
        raise ValueError('Expected schema 1 and ap-northeast-2')
    for k in ('project', 'environment'):
        if not NAME.fullmatch(c[k]):
            raise ValueError(f'Invalid {k}')
    ids = account_ids(c)
    if len(c['accounts']) != 5 or set(ids) != set(PROFILES):
        raise ValueError('Exactly the five approved encore profiles are required')
    if any(not isinstance(v, str) or not re.fullmatch(r'[0-9]{12}', v) for v in ids.values()) or len(set(ids.values())) != 5:
        raise ValueError('Five distinct 12-digit account IDs as strings are required')
    principal = c.get('operator_principal_arn', '')
    if not re.fullmatch(r'arn:aws:iam::' + ids['encore1'] + r':user/[A-Za-z0-9+=,.@_/-]+', principal):
        raise ValueError('operator_principal_arn must be an IAM user in encore1')
    if len(c['peering_pairs']) != 7 or {tuple(x) for x in c['peering_pairs']} != PAIRS:
        raise ValueError('Expected the seven approved direct peering pairs')
    if set(c['az_ids']) != {'a', 'b', 'c'}:
        raise ValueError('Exactly three physical AZ slots required')
    azs = [v for v in c['az_ids'].values() if v]
    if len(set(azs)) != len(azs) or any(not re.fullmatch(r'apne2-az[1-4]', v) for v in azs):
        raise ValueError('AZ IDs must be unique Seoul physical AZ IDs')
    web_port(c)
    for role in ('postgresql','mongodb'):
        port=c['service_ports'].get(role)
        if port is not None and (type(port) is not int or not 1<=port<=65535):
            raise ValueError('Invalid service port: '+role)
    if c['alb'].get('protocol','HTTPS') not in ('HTTP','HTTPS'):
        raise ValueError('ALB protocol must be HTTP or HTTPS')
    networks, names, ips, nodes = [], set(), set(), []
    expected = {'encore1': {'control', 'postgresql'}, 'encore2': {'kafka','spark','es'},
                'encore3': {'kafka','spark','es'}, 'encore4': {'kafka','spark','es'},
                'encore5': {'advertising','mongodb'}}
    for a in c['accounts']:
        net = ipaddress.ip_network(a['cidr'])
        if net.version != 4 or not net.is_private or net.prefixlen != 16 or any(net.overlaps(n) for n in networks):
            raise ValueError('Unique private /16 VPC CIDRs required')
        networks.append(net)
        if a['nat_slot'] not in 'abc' or len(a['nat_slot']) != 1:
            raise ValueError('Invalid NAT AZ slot')
        if {n['role'] for n in a['nodes']} != expected[a['profile']]:
            raise ValueError('Role/account placement differs from the approved topology')
        for n in a['nodes']:
            if not NAME.fullmatch(n['name']) or n['name'] in names or n['private_ip'] in ips:
                raise ValueError('Duplicate/invalid node or IP')
            names.add(n['name']); ips.add(n['private_ip']); nodes.append(n)
            if n['az_slot'] not in ('a','b','c'):
                raise ValueError('Invalid node AZ slot')
            subnet = ipaddress.ip_network(subnet_cidr(a, n['az_slot'], private=True))
            if not subnet.subnet_of(net):raise ValueError('Subnet must belong to the account VPC')
            ip = ipaddress.ip_address(n['private_ip'])
            if ip not in subnet or int(ip) - int(subnet.network_address) < 4 or ip == subnet.broadcast_address:
                raise ValueError('Node IP must belong to its private subnet and avoid AWS reserved addresses')
    if len(nodes) != 14 or {r: sum(n['role'] == r for n in nodes) for r in ROLES} != ROLES:
        raise ValueError('Expected 14 EC2s and the approved role counts')
    for role in ('kafka','spark','es'):
        if {n['az_slot'] for n in nodes if n['role'] == role} != {'a','b','c'}:
            raise ValueError('Each data cluster must span three physical AZs')
    if len({n['az_slot'] for n in nodes if n['role'] == 'control'}) != 2:
        raise ValueError('Controls must be in distinct physical AZs')
    if any(len(role_name(c,n['name']))>64 for n in nodes) or any(len(artifact_bucket(c,a))>63 for a in c['accounts']):
        raise ValueError('Project/environment prefix exceeds IAM role or S3 bucket name length')
    return c


def subnet_cidr(account, slot, private):
    start=int(ipaddress.ip_network(account['cidr']).network_address)
    return str(ipaddress.ip_network((start+((16 if private else 0)+"abc".index(slot))*256,24)))


def prefix(c):
    return f"{c['project']}-{c['environment']}"


def stack_name(c, profile, kind):
    return f'{prefix(c)}-{profile}-{kind}'


def role_name(c, node):
    return f'{prefix(c)}-{node}-runtime'


def artifact_bucket(c, account):
    return f"{prefix(c)}-{account['account_id']}-artifacts"


def checkpoint_bucket(c):
    return f"{prefix(c)}-{account_ids(c)['encore1']}-checkpoints"


def checkpoint_prefix(c):
    return f"aws/{c['environment']}/{c['generation']}/"


def account_budget_cap(c, profile):
    """Explicit account overrides, with the existing uniform cap as fallback."""
    budget = c['budget']
    overrides = budget.get('account_usd_caps', {})
    if not isinstance(overrides, dict) or set(overrides) - set(PROFILES):
        raise ValueError('budget.account_usd_caps must name only the five approved profiles')
    cap = overrides.get(profile, budget.get('per_account_usd_cap'))
    if type(cap) not in (int, float) or not Decimal(str(cap)).is_finite() or cap <= 0:
        raise ValueError('budget.account_usd_caps.' + profile + ' must be positive')
    return cap


def blockers(c, phase='compute'):
    """Unselected values stay unselected, never become billable defaults."""
    missing = []
    if phase in ('network','compute','alb','install'):
        missing += [f'az_ids.{k}' for k,v in c['az_ids'].items() if not v]
        if not c.get('network_reviewed'):
            missing.append('network_reviewed (VPC + connected LAN/VPN CIDR review)')
        if c['budget'].get('estimate_accepted') is not True:
            missing.append('budget.estimate_accepted (actual selected specs cost review)')
        for k in ('duration_hours','total_usd_cap','per_account_usd_cap','daily_ec2_hours'):
            if type(c['budget'].get(k)) not in (int,float) or c['budget'][k] <= 0:
                missing.append('budget.' + k)
        try:
            caps = [Decimal(str(account_budget_cap(c, a['profile']))) for a in c['accounts']]
            total = c['budget'].get('total_usd_cap')
            if type(total) in (int, float) and Decimal(str(total)) < sum(caps):
                missing.append('budget.total_usd_cap must cover all per-account caps')
        except ValueError as e:
            missing.append(str(e))
        if isinstance(c['budget'].get('daily_ec2_hours'), (int,float)) and c['budget']['daily_ec2_hours'] > 24:
            missing.append('budget.daily_ec2_hours must be <=24')
    if phase in ('compute','install'):
        if not re.fullmatch(r'ami-[0-9a-f]{8,17}', c.get('ami_id') or ''):
            missing.append('ami_id (verified Canonical Ubuntu 24.04 amd64)')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,31}', c.get('generation') or ''):
            missing.append('generation (explicit new installation ID)')
        for a in c['accounts']:
            for n in a['nodes']:
                for k in ('instance_type','root_gib','data_gib','cpu','memory_mib','min_free_disk_gib'):
                    v = n.get(k)
                    if k == 'instance_type':
                        valid = isinstance(v,str) and re.fullmatch(r'[a-z0-9]+\.[a-z0-9]+',v)
                    else:
                        valid = type(v) is int and v >= (8 if k == 'root_gib' else 1)
                    if not valid:
                        missing.append(n['name'] + '.' + k)
                if (n.get('instance_type') or '').startswith('t3.') and n.get('credit_mode') != 'standard':
                    missing.append(n['name'] + '.credit_mode (selected budget requires standard)')
                if n['role'] in ('kafka','es'):
                    key = 'heap' if n['role'] == 'kafka' else 'es_heap'
                    if not re.fullmatch(r'[1-9][0-9]*[gm]', n.get(key) or ''):
                        missing.append(n['name'] + '.' + key)
                if n['role'] == 'spark':
                    for k in ('worker_cores','worker_memory','reserved_memory_mib'):
                        if n.get(k) is None:
                            missing.append(n['name'] + '.' + k)
    if phase == 'alb':
        required=['allowed_client_cidr','health_path']
        if c['alb'].get('protocol','HTTPS')=='HTTPS':required.append('certificate_arn')
        for k in required:
            if not c['alb'].get(k): missing.append('alb.' + k)
        if not web_port(c): missing.append('service_ports.web')
        client = c['alb'].get('allowed_client_cidr')
        if client:
            try:
                network = ipaddress.ip_network(client)
                if network.version != 4 or network.prefixlen == 0:
                    missing.append('alb.allowed_client_cidr must be restricted IPv4')
            except (ValueError, TypeError):
                missing.append('alb.allowed_client_cidr must be valid IPv4 CIDR')
        health = c['alb'].get('health_path')
        if health and (not isinstance(health, str) or not health.startswith('/') or
                       any(ord(char) < 33 or ord(char) > 126 for char in health)):
            missing.append('alb.health_path must be an absolute HTTP path without whitespace')
        cert = c['alb'].get('certificate_arn')
        if c['alb'].get('protocol','HTTPS') == 'HTTPS' and cert and not re.fullmatch(
                r'arn:aws:acm:ap-northeast-2:' + account_ids(c)['encore1'] + r':certificate/[a-f0-9-]+', cert):
            missing.append('alb.certificate_arn must belong to encore1 in Seoul')
    return missing
