"""Install the reviewed Spark/Scala/Hadoop connector bytes on an idle cluster.

The deployer supplies an owner-only plan with exact instance_id, generation,
and all three master_hosts; this command does not discover or create resources.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from urllib.request import Request, urlopen


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def validate(bundle, spark_home):
    published = json.loads(Path(__file__).with_name('connectors.lock.json').read_text())
    supplied = json.loads((bundle / 'connectors.lock.json').read_text())
    if published != supplied or published['schema_version'] != 2:
        raise RuntimeError('bundle_differs_from_reviewed_lock')
    if (published['spark_version'], published['hadoop_version']) != ('4.1.3', '3.4.2'):
        raise RuntimeError('runtime_version_mismatch')
    jars = spark_home / 'jars'
    entries = published['distribution_jars'] + published['jars']
    expected = {j['filename'] for j in entries}
    if len(entries) != len(expected) or any(p.name not in expected for p in jars.glob('*.jar')):
        raise RuntimeError('unreviewed_or_duplicate_jar')
    for entry in entries:
        name = entry['filename']
        if Path(name).name != name or not name.endswith('.jar'):
            raise RuntimeError('invalid_jar_filename')
        target = jars / name
        source = target if entry in published['distribution_jars'] else bundle / name
        if source.is_symlink() or not source.is_file() or digest(source) != entry['sha256']:
            raise RuntimeError('jar_checksum_mismatch')
        if target.is_symlink() or target.exists() and digest(target) != entry['sha256']:
            raise RuntimeError('existing_jar_conflict')
    return published


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--spark-home', type=Path, default=Path('/opt/music-cluster/spark'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('EC2_root_required')
    plan = json.loads(args.plan.read_text())
    receipt = Path('/var/lib/music-cluster/aws-state') / plan['generation'] / 'common.json'
    if not receipt.is_file():
        raise RuntimeError('installed_generation_required')
    token = urlopen(Request('http://169.254.169.254/latest/api/token', method='PUT',
                    headers={'X-aws-ec2-metadata-token-ttl-seconds':'60'}), timeout=3).read().decode()
    instance = urlopen(Request('http://169.254.169.254/latest/meta-data/instance-id',
                       headers={'X-aws-ec2-metadata-token':token}), timeout=3).read().decode()
    if instance != plan['instance_id'] or len(set(plan['master_hosts'])) != 3:
        raise RuntimeError('instance_or_master_plan_mismatch')
    states = []
    for host in plan['master_hosts']:
        import ipaddress
        if not ipaddress.ip_address(host).is_private:
            raise RuntimeError('private_master_required')
        with urlopen('http://' + host + ':8080/json/', timeout=10) as response:
            states.append(json.load(response))
    if sorted(v['status'] for v in states) != ['ALIVE','STANDBY','STANDBY'] or any(v.get('activeapps') != [] for v in states):
        raise RuntimeError('unique_idle_cluster_required')
    manifest = validate(args.bundle, args.spark_home)
    if args.apply:
        for entry in manifest['jars']:
            target = args.spark_home / 'jars' / entry['filename']
            if not target.exists():
                shutil.copyfile(args.bundle / entry['filename'], target)
                target.chmod(0o644)
        target = args.spark_home / 'connectors.lock.json'
        if target.is_symlink(): raise RuntimeError('unsafe_installed_lock')
        shutil.copyfile(args.bundle / 'connectors.lock.json', target)
        target.chmod(0o644)
    print(json.dumps({'applied':args.apply, 'reviewed_addon_jars':len(manifest['jars']),
                      'spark_version':manifest['spark_version'], 'online_resolution':False}))


if __name__ == '__main__':
    main()
