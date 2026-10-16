"""AWS CLI v2 transport using the Control instance profile, never local profiles."""
import json
import os
from pathlib import Path
import re
import subprocess

from control_fencing import FencingError


class InstanceAws:
    def __init__(self, region, binary, expected_version, env=None):
        self.region, self.binary = region, binary
        if region != 'ap-northeast-2' or not Path(binary).is_absolute():
            raise FencingError('Seoul region and explicit AWS CLI binary required')
        self.env = {k: v for k, v in (os.environ if env is None else env).items() if not k.startswith('AWS_')}
        self.env.update(AWS_CONFIG_FILE='/dev/null', AWS_SHARED_CREDENTIALS_FILE='/dev/null',
            AWS_EC2_METADATA_DISABLED='false', AWS_PAGER='', AWS_MAX_ATTEMPTS='1', AWS_RETRY_MODE='standard')
        version = subprocess.run([binary, '--version'], env=self.env, capture_output=True, text=True, timeout=10)
        if not re.fullmatch(r'2\.[0-9]+\.[0-9]+', expected_version) or version.returncode or not version.stdout.startswith('aws-cli/' + expected_version + ' '):
            raise FencingError('Install the reviewed exact AWS CLI v2 version before activation')

    def call(self, service, operation, *args):
        command = [self.binary, '--region', self.region, '--no-cli-pager', '--output', 'json',
                   '--cli-connect-timeout', '5', '--cli-read-timeout', '10', service, operation, *map(str, args)]
        try:
            result = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired as error:
            raise FencingError('AWS request outcome unknown; retain ownership and inspect before retry') from error
        if result.returncode:
            # CLI stderr can contain identity/configuration details. Never
            # include command parameters, credentials or raw output in logs.
            raise FencingError('AWS CLI operation failed: ' + service + '/' + operation)
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def verify_control(self, account_id, role_name, instance_id):
        identity = self.call('sts', 'get-caller-identity')
        expected = 'arn:aws:sts::' + account_id + ':assumed-role/' + role_name + '/' + instance_id
        if identity.get('Account') != account_id or identity.get('Arn') != expected:
            raise FencingError('AWS credentials must be the expected Control instance profile')

    def observer(self, node, external_id):
        # Construct a fresh short session for each observation; never write
        # temporary credentials to disk or keep expired cross-account clients.
        result = self.call('sts', 'assume-role', '--role-arn', node['observer_role_arn'],
            '--role-session-name', 'control-spark-observe', '--external-id', external_id,
            '--duration-seconds', '900')['Credentials']
        child = object.__new__(InstanceAws)
        child.binary, child.region, child.env = self.binary, self.region, self.env.copy()
        child.env.update(AWS_ACCESS_KEY_ID=result['AccessKeyId'], AWS_SECRET_ACCESS_KEY=result['SecretAccessKey'],
                         AWS_SESSION_TOKEN=result['SessionToken'])
        return child
