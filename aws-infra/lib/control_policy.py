"""Opt-in owner-reviewed IAM/SSM templates; absent from ordinary create/setup."""
import json
from pathlib import Path

from templates import allow, attr, base, doc, output, param, ref, resource, sub

ROOT = Path(__file__).resolve().parents[1]


def common(description):
    value = base(description)
    value['Metadata']['com.aws.cloudformation.Context'] = {
        'ref': ['../docs/handoff/infra/CONTROL-FENCING.md'],
        'must': ['Owner-reviewed opt-in; ordinary create/setup never applies this stack.',
                 'No EC2 creation/replacement, inbound changes, start/terminate or checkpoint reset.']}
    for name in ('Project', 'Environment'):
        param(value, name, r'[a-z][a-z0-9-]{0,23}')
    param(value, 'Generation', r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}')
    return value


def external_id():
    return sub('${Project}:${Environment}:${Generation}:spark-observe')


def controls_template():
    value = common('Opt-in peer-only Control stop permissions and three read-only Spark observer role assumptions.')
    for name in ('A', 'B'):
        param(value, 'Control' + name + 'InstanceId', r'i-[0-9a-f]{8,17}')
        param(value, 'Control' + name + 'RoleName', r'[a-zA-Z0-9+=,.@_-]{1,64}')
    for number in (1, 2, 3):
        param(value, f'Observer{number}RoleArn', r'arn:aws:iam::[0-9]{12}:role/[a-zA-Z0-9+=,.@_/-]+')
    for name, peer in (('A', 'B'), ('B', 'A')):
        policy = doc([
            allow('ec2:DescribeInstances', '*', Condition={'StringEquals': {'aws:RequestedRegion': ref('AWS::Region')}}),
            allow('ec2:StopInstances', sub('arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:instance/${Control' + peer + 'InstanceId}'),
                  Condition={'StringEquals': {'aws:RequestedRegion': ref('AWS::Region'),
                      'ec2:ResourceTag/Project': ref('Project'), 'ec2:ResourceTag/Environment': ref('Environment'),
                      'ec2:ResourceTag/Node': 'control-' + peer.lower(), 'ec2:ResourceTag/Role': 'control'}}),
            allow('sts:AssumeRole', [ref(f'Observer{n}RoleArn') for n in (1, 2, 3)],
                  Condition={'StringEquals': {'sts:ExternalId': external_id()}}),
        ])
        resource(value, 'Control' + name + 'FencePolicy', 'AWS::IAM::Policy', {
            'PolicyName': sub('${AWS::StackName}-control-' + name.lower()),
            'Roles': [ref('Control' + name + 'RoleName')], 'PolicyDocument': policy},
            'The exact peer instance ARN pins the reviewed generation; current EC2s have no Generation tag.',
            ['Never use a stop wildcard, grant self-stop/start/terminate, or infer identity from mutable tags alone.',
             'Re-render/review exact IDs after replacement; existing runtime role trust and other policies remain unchanged.'])
    return value


def observer_template():
    value = common('Opt-in read-only Spark SSM observation document and role trusted only by the two Control roles.')
    for name in ('A', 'B'):
        param(value, 'Control' + name + 'RoleArn', r'arn:aws:iam::[0-9]{12}:role/[a-zA-Z0-9+=,.@_/-]+')
    param(value, 'SparkInstanceId', r'i-[0-9a-f]{8,17}')
    param(value, 'SparkPrivateIp', r'[0-9]{1,3}(\.[0-9]{1,3}){3}')
    param(value, 'NodeName', AllowedValues=['spark-01', 'spark-02', 'spark-03'])
    expected = {k: '${' + v + '}' for k, v in {
        'project': 'Project', 'environment': 'Environment', 'generation': 'Generation', 'node': 'NodeName',
        'instance_id': 'SparkInstanceId', 'private_ip': 'SparkPrivateIp',
        'account_id': 'AWS::AccountId', 'region': 'AWS::Region'}.items()}
    source = (ROOT / 'installer/control-observe.py').read_text().split("if __name__ == '__main__':")[0]
    command = ("set -eu\numask 077\npython3 - <<'FIXED_SPARK_OBSERVER'\n" + source +
        "\nif sys.platform != 'linux' or os.geteuid() != 0: raise SystemExit('Linux SSM root required')\n" +
        'expected = json.loads(' + repr(json.dumps(expected)) + ')\n' +
        "print(json.dumps(collect(expected, os.environ['SSM_ObservationNonce'])))\nFIXED_SPARK_OBSERVER")
    content = {'schemaVersion': '2.2', 'description': 'Read-only local Spark membership/process observation; fixed instance and mounted generation.',
        'parameters': {'ObservationNonce': {'type': 'String', 'allowedPattern': '^[0-9a-f]{32}$', 'interpolationType': 'ENV_VAR'}},
        'mainSteps': [{'action': 'aws:runShellScript', 'name': 'observeSpark',
            'precondition': {'StringEquals': ['platformType', 'Linux']},
            'inputs': {'timeoutSeconds': '30', 'runCommand': [sub(command)]}}]}
    resource(value, 'ObserverDocument', 'AWS::SSM::Document', {
        'Name': sub('${AWS::StackName}-observe'), 'DocumentType': 'Command', 'DocumentFormat': 'JSON',
        'UpdateMethod': 'NewVersion', 'Content': content,
        'Tags': [{'Key': 'Project', 'Value': ref('Project')}, {'Key': 'Environment', 'Value': ref('Environment')}]},
        'A nonce is the only caller input; code verifies IMDS and data generation, then reads local UIs and process counts.',
        ['Never accept commands, script URLs, arbitrary runtime paths or alternate target addresses.',
         'Pin actual document version and SHA256 in private runtime; missing ENV_VAR support fails closed.'])
    document_arn = sub('arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:document/${ObserverDocument}')
    policy = doc([
        allow('ssm:SendCommand', sub('arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:instance/${SparkInstanceId}'),
              Condition={'StringEquals': {'aws:RequestedRegion': ref('AWS::Region'),
                  'ssm:resourceTag/Project': ref('Project'), 'ssm:resourceTag/Environment': ref('Environment'),
                  'ssm:resourceTag/Node': ref('NodeName')}}),
        allow('ssm:SendCommand', document_arn, Condition={'StringEquals': {'aws:RequestedRegion': ref('AWS::Region')}}),
        allow(['ssm:ListCommandInvocations', 'ssm:GetCommandInvocation'], '*',
              Condition={'StringEquals': {'aws:RequestedRegion': ref('AWS::Region')}}),
        allow(['ssm:DescribeDocument', 'ssm:GetDocument'], document_arn,
              Condition={'StringEquals': {'aws:RequestedRegion': ref('AWS::Region')}}),
    ])
    resource(value, 'ObserverRole', 'AWS::IAM::Role', {
        'RoleName': sub('${AWS::StackName}-observer'),
        'AssumeRolePolicyDocument': doc([{'Effect': 'Allow', 'Principal': {'AWS': [ref('ControlARoleArn'), ref('ControlBRoleArn')]},
            'Action': 'sts:AssumeRole', 'Condition': {'StringEquals': {'sts:ExternalId': external_id()}}}]),
        'Policies': [{'PolicyName': 'fixed-spark-observation', 'PolicyDocument': policy}],
        'Tags': [{'Key': 'Project', 'Value': ref('Project')}, {'Key': 'Environment', 'Value': ref('Environment')}]},
        'Control role principals need an ExternalId; no service SourceArn condition is invented for role-to-role STS.',
        ['No AWS-RunShellScript/AWS-RunRemoteScript or arbitrary root command permission.',
         'SSM result-read APIs lack resource scoping; regional account command-output read is the explicit remaining breadth.'])
    output(value, 'ObserverRoleArn', attr('ObserverRole', 'Arn'), 'Control assumption target; bind from actual stack output')
    output(value, 'ObserverDocumentName', ref('ObserverDocument'), 'Read-only document; additionally pin actual version and hash')
    return value
