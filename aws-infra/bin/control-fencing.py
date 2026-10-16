#!/usr/bin/env python3
"""Offline Control proposal/packages; installation and activation stay explicit."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'bin'), str(ROOT / 'lib')]
sys.path.append(str(ROOT / 'installer/core/lib'))
from config import ZK_TLS_PORT
import install
from control_fencing import Owner
from control_policy import controls_template, observer_template
from infra import account
from manage import write
from project import artifact_bucket, load, prefix, role_name
from revision import source_identity

MODULES = ('control_fencing.py', 'control_coordinator.py', 'control_runtime.py', 'control_observation.py', 'control_aws.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bundle_checked(path):
    path = Path(path)
    published = json.loads((ROOT / 'installer/control-fencing.lock.json').read_text())
    if path.is_symlink() or json.loads((path / 'control-fencing.lock.json').read_text()) != published:
        raise ValueError('Reviewed fencing dependency lock required')
    expected = {p['filename'] for p in published['packages']} | {'control-fencing.lock.json'}
    if {p.name for p in path.iterdir()} != expected:
        raise ValueError('Incomplete/extra fencing runtime artifacts')
    for package in published['packages']:
        name = package['filename']
        if Path(name).name != name or not name.endswith('.whl') or (path / name).is_symlink() or sha(path / name) != package['sha256']:
            raise ValueError('Fencing dependency byte identity differs')
    return published


def stack_names(c):
    identity = hashlib.sha256(prefix(c).encode()).hexdigest()[:8]
    base = prefix(c)[:32]
    return {'observer': base + '-fo-' + identity, 'controls': base + '-fc-' + identity}


def scoped_config(path):
    c = load(path)
    if not c.get('generation'):
        current = ROOT / '.state/lifecycle' / prefix(c) / 'current.json'
        state = json.loads(current.read_text())
        if state['state'] != 'ready' or state['source_sha256'] != sha(path):
            raise ValueError('Use the unchanged active lifecycle config')
        c = load(state['resolved_config'])
    return c


def plan(c, bundle):
    try:
        lock = bundle_checked(bundle);ready = True
    except (OSError, ValueError, KeyError):
        lock = None;ready = False
    return {'mode': 'offline; no AWS calls, resource changes or workload activation', 'implementation': source_identity(),
        'control_lease_ec2_spark_adapters_implemented': True, 'connection_loss_supervision_implemented': True,
        'promotion_policy': 'all three Masters and all three Workers globally idle; otherwise blocked',
        'runtime_bundle_verified': ready, 'runtime_packages': len(lock['packages']) if lock else 0,
        'opt_in_owner_review_templates': 4, 'default_create_setup_changed': False,
        'runtime_installed': False, 'live_control_stop_or_takeover_verified': False, 'concurrent_s3_writer_fencing_verified': False,
        'required_before_activation': ['Review/apply three exact-instance read-only observer IAM/SSM stacks and the peer-only Control IAM stack',
            'Record actual document versions/hashes plus fresh Control VPC/ENI identities in private bindings',
            'Install exact reviewed AWS CLI v2 on Control; prepare/install separate signed-by-hash node packages with no automatic unit start',
            'Explicitly bootstrap the dedicated TLS+SASL+digest ACL namespace; never reset epoch/owner/checkpoint state',
            'Run the isolated canary, lease-loss, physical peer-stop and S3 concurrent-writer/takeover acceptance tests'],
        'business_application_source_required_for_preparation': False}


def render_proposal(c, inventory, out):
    install.checked_inventory(c, inventory)
    out = Path(out).resolve()
    if not out.is_relative_to((ROOT / '.state').resolve()):
        raise ValueError('Actual IAM proposals belong in ignored .state')
    if out.exists():
        raise ValueError('Proposal directory exists; preserve and explicitly review a new output directory')
    out.mkdir(parents=True, mode=0o700)
    names = stack_names(c);controls = [n for n in inventory['nodes'] if n['role'] == 'control']
    owner = account(c, 'encore1');control_arns = {n['name']: 'arn:aws:iam::' + owner['account_id'] + ':role/' + role_name(c, n['name']) for n in controls}
    parameter = lambda k, v: {'ParameterKey': k, 'ParameterValue': v}
    shared = [parameter(k.capitalize(), c[k]) for k in ('project', 'environment', 'generation')]
    jobs = [];observer_arns = []
    for index, node in enumerate([n for n in inventory['nodes'] if n['role'] == 'spark'], 1):
        template = out / (node['profile'] + '-observer.template.json');write(template, observer_template())
        params = shared + [parameter('ControlARoleArn', control_arns['control-a']), parameter('ControlBRoleArn', control_arns['control-b']),
            parameter('SparkInstanceId', node['instance_id']), parameter('SparkPrivateIp', node['private_ip']), parameter('NodeName', node['name'])]
        path = out / (node['profile'] + '-observer.parameters.json');write(path, params)
        jobs.append({'profile': node['profile'], 'stack_name': names['observer'], 'template': str(template), 'parameters': str(path)})
        observer_arns.append('arn:aws:iam::' + node['account_id'] + ':role/' + names['observer'] + '-observer')
    params = shared[:]
    for letter in ('A', 'B'):
        node = next(n for n in controls if n['name'] == 'control-' + letter.lower())
        params += [parameter('Control' + letter + 'InstanceId', node['instance_id']), parameter('Control' + letter + 'RoleName', role_name(c, node['name']))]
    params += [parameter(f'Observer{n}RoleArn', arn) for n, arn in enumerate(observer_arns, 1)]
    template = out / 'encore1-controls.template.json';write(template, controls_template())
    path = out / 'encore1-controls.parameters.json';write(path, params)
    jobs.append({'profile': 'encore1', 'stack_name': names['controls'], 'template': str(template), 'parameters': str(path)})
    write(out / 'proposal.json', {'implementation': source_identity(), 'generation': c['generation'], 'inventory_sha256': hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
        'apply_order': jobs, 'applied': False, 'fresh_identity_and_owner_review_required': True,
        'notice': 'Use account administrators; current scoped CF execution roles cannot grant themselves these IAM changes.'})
    return {'templates_prepared': 4, 'aws_changes_executed': False, 'control_stop_permissions': 'exact peer ARN only', 'observer_document': 'nonce-only fixed read-only code'}


def prepare(c, inventory, bindings, query, bundle):
    """A separate two-node payload leaves the fourteen foundation packages intact."""
    install.checked_inventory(c, inventory);lock = bundle_checked(bundle)
    controls = {n['name']: n for n in inventory['nodes'] if n['role'] == 'control'}
    for n in controls.values():
        Owner(c['project'], c['environment'], c['generation'], query, n['name'], n['instance_id'], 0)
    if bindings.get('generation') != c['generation'] or set(bindings['controls']) != set(controls):
        raise ValueError('Fresh generation-scoped Control/observer bindings required')
    names = stack_names(c);spark_nodes = [n for n in inventory['nodes'] if n['role'] == 'spark'];members = []
    for n in spark_nodes:
        b = bindings['spark'][n['name']]
        expected_arn = 'arn:aws:iam::' + n['account_id'] + ':role/' + names['observer'] + '-observer'
        if (b['instance_id'] != n['instance_id'] or b['observer_role_arn'] != expected_arn or
            b['observer_document'] != names['observer'] + '-observe' or not re.fullmatch(r'[1-9][0-9]*', b['observer_document_version']) or
            not re.fullmatch(r'[0-9a-f]{64}', b['observer_document_hash'])):
            raise ValueError('Owner-reviewed actual observer version/hash/identity bindings required')
        members.append({**{k: c[k] for k in ('project', 'environment', 'generation', 'region')},
            'node': n['name'], **{k: n[k] for k in ('instance_id', 'private_ip', 'account_id')},
            **{k: b[k] for k in ('observer_role_arn', 'observer_document', 'observer_document_version', 'observer_document_hash')}})
    pair = {}
    for name, node in controls.items():
        b = bindings['controls'][name]
        if b['instance_id'] != node['instance_id'] or b['eni_id'] != node['eni_id'] or not re.fullmatch(r'vpc-[0-9a-f]{8,17}', b['vpc_id']):
            raise ValueError('Fresh Control VPC/instance/ENI mapping required')
        pair[name] = {**b, 'generation': c['generation'], 'private_ip': node['private_ip']}
    if not Path(bindings['aws_cli']).is_absolute() or not re.fullmatch(r'2\.[0-9]+\.[0-9]+', bindings['aws_cli_version']):
        raise ValueError('Exact reviewed AWS CLI v2 installation binding required')
    private = ROOT / '.private' / c['environment'] / c['generation'];base = private / 'control-fencing';base.mkdir(parents=True, exist_ok=True);base.chmod(0o700)
    secret = base / 'coordinator.json'
    if not secret.exists():
        if any(base.iterdir()):raise ValueError('Missing coordinator credential with existing state; never regenerate implicitly')
        write(secret, {'scope': [c['project'], c['environment'], c['generation']], 'password': secrets.token_urlsafe(48)})
    credential = json.loads(secret.read_text())
    if credential['scope'] != [c['project'], c['environment'], c['generation']]:
        raise ValueError('Coordinator private identity differs; do not rotate/reset implicitly')
    target = base / query
    if target.exists():
        raise ValueError('Prepared query exists; inspect its source and receipts before an explicit upgrade')
    target.mkdir(mode=0o700)
    env = dict(line.split('=', 1) for line in (private / 'secrets.env').read_text().splitlines() if line and not line.startswith('#'))
    identity = source_identity();lock_sha = sha(ROOT / 'installer/control-fencing.lock.json')
    home = '/opt/music-cluster/control-fencing/' + identity['source_sha256'];venv = '/var/lib/music-cluster/control/fencing-venv/' + lock_sha
    packages = []
    for name, node in controls.items():
        root = target / name;root.mkdir(mode=0o700)
        tls = '/etc/music-cluster/control/fencing/tls/'
        fencing = {'query': query, 'controls': pair, 'spark_members': members, 'zk_hosts': [n['private_ip'] + ':' + str(ZK_TLS_PORT) for n in spark_nodes],
            'sasl_password': env['ZK_HA_PASSWORD'], 'coordinator_password': credential['password'],
            'tls': {'ca': tls + 'ca.crt', 'certificate': tls + 'node.crt', 'key': tls + 'node.key'},
            'aws_cli': bindings['aws_cli'], 'aws_cli_version': bindings['aws_cli_version'], 'runtime_role_name': role_name(c, name),
            'source_sha256': identity['source_sha256'], 'dependency_lock_sha256': lock_sha,
            'workloads': [{'argv': [venv + '/bin/python', home + '/control-canary.py', '--directory', '/var/lib/music-cluster/control/fencing-canary/' + query],
                           'cwd': '/var/lib/music-cluster/control'}], 'workload_kind': 'isolated local canary; no business/S3 workload'}
        runtime = {'aws': {k: c[k] for k in ('project', 'environment', 'generation')}, 'node': {**node, 'address': node['private_ip'], 'roles': ['control']},
                   'env': {'ENVIRONMENT': 'aws', 'AWS_REGION': c['region']}, 'fencing': fencing}
        write(root / 'runtime.json', runtime)
        paths = [('runtime.json', root / 'runtime.json')]
        paths += [(file, ROOT / 'installer' / file) for file in ('aws-identity.py', 'init-disk.py', 'control-fencing.sh', 'control-runner.py', 'control-canary.py', 'control-fencing.lock.json')]
        paths += [('aws-bootstrap.sh', ROOT / 'installer/control-bootstrap.sh')]
        paths += [('fencing/' + file, ROOT / 'lib' / file) for file in MODULES]
        paths += [('wheels/' + p['filename'], Path(bundle) / p['filename']) for p in lock['packages']]
        paths += [('pki/' + p, private / 'pki' / (name if p != 'ca.crt' else '') / p) for p in ('ca.crt', 'node.crt', 'node.key')]
        archive = root / 'payload.tgz'
        with tarfile.open(archive, 'w:gz') as tar:
            for relative, path in install.safe_members(paths):
                info = tar.gettarinfo(str(path), arcname=relative);info.mode = 0o600;info.uid = info.gid = 0;info.uname = info.gname = 'root'
                with path.open('rb') as stream:tar.addfile(info, stream)
        checksum = sha(archive)
        packages.append({'implementation': identity, 'node': name, 'profile': node['profile'], 'instance_id': node['instance_id'], 'generation': c['generation'],
            'file': str(archive), 'sha256': checksum, 'bucket': artifact_bucket(c, account(c, node['profile'])),
            'key': 'private/' + name + '/' + c['generation'] + '/' + checksum + '/payload.tgz', 'control_fencing_lock_sha256': lock_sha})
    write(target / 'packages.json', packages)
    return {'control_packages_prepared': 2, 'foundation_packages_unchanged': True, 'installed': False, 'workload': 'canary only'}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--config', default=str(ROOT / 'config/project.json'))
    commands = parser.add_subparsers(dest='action', required=True)
    q = commands.add_parser('plan');q.add_argument('--bundle', default=str(ROOT / '.local/control-fencing/runtime'))
    q = commands.add_parser('render-proposal');q.add_argument('--inventory', required=True);q.add_argument('--out', required=True)
    q = commands.add_parser('prepare');q.add_argument('--inventory', required=True);q.add_argument('--bindings', required=True);q.add_argument('--query', required=True)
    q.add_argument('--bundle', default=str(ROOT / '.local/control-fencing/runtime'))
    q = commands.add_parser('send-install');q.add_argument('--query', required=True);q.add_argument('--node', required=True, choices=('control-a', 'control-b'))
    q.add_argument('--receipt', required=True);q.add_argument('--execute', action='store_true')
    args = parser.parse_args();c = load(args.config) if args.action == 'plan' else scoped_config(args.config)
    if args.action == 'plan':report = plan(c, args.bundle)
    elif args.action == 'render-proposal':report = render_proposal(c, json.loads(Path(args.inventory).read_text()), args.out)
    elif args.action == 'prepare':
        with (ROOT / '.state/lifecycle' / prefix(c) / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            report = prepare(c, json.loads(Path(args.inventory).read_text()), json.loads(Path(args.bindings).read_text()), args.query, args.bundle)
    else:
        Owner(c['project'], c['environment'], c['generation'], args.query, args.node, 'i-00000000000000001', 0)
        receipt = Path(args.receipt).resolve()
        if not receipt.is_relative_to((ROOT / '.state').resolve()):raise ValueError('Install receipt must remain under .state')
        if not args.execute:
            report = {'executed': False, 'stage': 'control-fencing', 'unit_started': False}
        else:
            with (ROOT / '.state/lifecycle' / prefix(c) / 'lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                packages = ROOT / '.private' / c['environment'] / c['generation'] / 'control-fencing' / args.query / 'packages.json'
                install.send(c, args.node, 'control-fencing', receipt, None, package_manifest=packages)
            return
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:main()
    except Exception as error:sys.exit('[FAIL] Fencing preparation blocked (' + type(error).__name__ + '); inspect private inputs, no automatic reset')
