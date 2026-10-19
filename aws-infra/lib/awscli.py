"""AWS CLI adapter. Credentials never appear in stored state or tool output."""
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from project import account_ids, prefix


class AwsError(RuntimeError): pass


class Aws:
    def __init__(self,c,account,admin=False,raw=False):
        if c.get('example_only') is not False:
            raise AwsError('Use an ignored local config with example_only=false; example configuration cannot contact AWS')
        self.c=c; self.account=account; self.env=os.environ.copy(); self.profile=account['profile']
        if admin:
            self.profile=account.get('admin_profile') or ('encore1' if self.profile=='encore1' else None)
            if not self.profile:
                raise AwsError('Account administrator profile is required for bootstrap/acceptor; ProjectInfraRole cannot grant IAM privileges to itself')
        identity=self.call('sts','get-caller-identity')
        if identity['Account']!=account['account_id']:
            raise AwsError('Profile resolves to the wrong account')
        if account['profile']=='encore1' and not admin and not raw:
            role=f"arn:aws:iam::{account_ids(c)['encore1']}:role/{prefix(c)}-operator"
            session=self.call('sts','assume-role','--role-arn',role,'--role-session-name','music-infra-cli')['Credentials']
            self.env.update(AWS_ACCESS_KEY_ID=session['AccessKeyId'],AWS_SECRET_ACCESS_KEY=session['SecretAccessKey'],AWS_SESSION_TOKEN=session['SessionToken'])
            self.expiration=datetime.fromisoformat(session['Expiration'].replace('Z','+00:00'))
            self.profile=None
        else:self.expiration=None

    def call(self,service,operation,*args):
        if getattr(self,'expiration',None) and (self.expiration-datetime.now(timezone.utc)).total_seconds()<60:
            raise AwsError('Operator session expires soon; rerun the explicit command to resume')
        cmd=['aws','--region',self.c['region'],'--no-cli-pager','--output','json',
             '--cli-connect-timeout','10','--cli-read-timeout','40']
        if self.profile:cmd+=['--profile',self.profile]
        try:
            r=subprocess.run(cmd+[service,operation,*map(str,args)],env=self.env,capture_output=True,text=True,timeout=90)
        except subprocess.TimeoutExpired:
            raise AwsError(f'{service}/{operation}: request outcome unknown; inspect saved state before retrying a mutation') from None
        if r.returncode:
            # Only AWS errors, no command parameter payloads or environment values.
            error=r.stderr.strip()
            if operation=='assume-role': error='Unable to assume the configured operator role; verify bootstrap and current encore1 login'
            raise AwsError(f'{service}/{operation}: {error}')
        return json.loads(r.stdout) if r.stdout.strip() else {}


def wait_until(fn,predicate,seconds=1800,interval=10):
    end=time.monotonic()+seconds
    while True:
        value=fn()
        if predicate(value):return value
        if time.monotonic()>=end:raise AwsError('Timeout; state retained, inspect and resume explicitly')
        time.sleep(interval)
