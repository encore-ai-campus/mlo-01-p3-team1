#!/usr/bin/env python3
"""Verify EC2 identity through IMDSv2 without fetching/exporting AWS credentials."""
import json
import sys
from pathlib import Path
from urllib.request import Request,urlopen,build_opener,ProxyHandler


def verify(c,fetch):
    if c['env'].get('ENVIRONMENT')!='aws' or not c['aws'].get('generation'):
        raise ValueError('AWS environment/generation required')
    actual=fetch()
    expected=c['node']
    if (actual['accountId']!=expected['account_id'] or actual['instanceId']!=expected['instance_id']
        or actual['privateIp']!=expected['address'] or actual['region']!=c['env']['AWS_REGION']):
        raise ValueError('EC2 identity does not match account, InstanceId, private IP and region')


def identity():
    base='http://169.254.169.254/latest/'
    opener=build_opener(ProxyHandler({}))
    req=Request(base+'api/token',method='PUT',headers={'X-aws-ec2-metadata-token-ttl-seconds':'60'})
    with opener.open(req,timeout=5) as r:token=r.read().decode()
    req=Request(base+'dynamic/instance-identity/document',headers={'X-aws-ec2-metadata-token':token})
    with opener.open(req,timeout=5) as r:return json.load(r)


if __name__=='__main__':
    try:
        verify(json.loads(Path(sys.argv[1]).read_text()),identity)
        print('[PASS] Verified EC2 IMDSv2 account/instance/private-IP/region identity')
    except Exception:
        sys.exit('[FAIL] AWS EC2 identity preflight failed; no installation performed')
