"""Namespaced synthetic probes never reuse or delete a business checkpoint."""
import re


def checkpoint_paths(runtime, run_id):
    if runtime['env'].get('ENVIRONMENT') != 'aws':
        raise ValueError('AWS-only checkpoint probe')
    aws = runtime['aws']
    for key in ('project', 'environment', 'generation'):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}', aws[key]):
            raise ValueError('Invalid checkpoint namespace')
    if not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise ValueError('Explicit unique 32-hex test run ID required')
    prefix = 'aws/' + aws['environment'] + '/' + aws['generation'] + '/'
    if runtime['env'].get('S3_CHECKPOINT_PREFIX') != prefix:
        raise ValueError('Checkpoint prefix differs from this installation generation')
    bucket = runtime['env'].get('S3_BUCKET', '')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket) or '..' in bucket:
        raise ValueError('Valid provisioned checkpoint bucket required')
    if not re.fullmatch(re.escape(aws['project']+'-'+aws['environment']+'-')+r'[0-9]{12}-checkpoints',bucket):
        raise ValueError('Probe must use this project/environment checkpoint bucket')
    base = 's3a://' + bucket + '/' + prefix + '_infra-tests/checkpoint-' + run_id
    return {name: base + '/' + name for name in ('input', 'output', 'checkpoint')}
