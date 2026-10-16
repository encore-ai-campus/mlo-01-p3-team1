"""Only additive ingress on an existing, ownership-verified Control security group."""
import ipaddress


def template(addresses):
    addresses = sorted({str(ipaddress.ip_address(ip)) + '/32' for ip in addresses})
    resources = {}
    parameters = {'ControlGroup': {'Type': 'AWS::EC2::SecurityGroup::Id'}}
    for index, address in enumerate(addresses, 1):
        key = 'Node' + str(index)
        parameters[key] = {'Type': 'String', 'AllowedPattern': r'\d{1,3}(\.\d{1,3}){3}/32'}
        resources['LogGatewayIngress' + str(index)] = {
            'Type': 'AWS::EC2::SecurityGroupIngress',
            'Metadata': {'com.aws.cloudformation.Context': {
                'why': 'Private log transport through Control B to avoid transitive VPC peering.',
                'must': ['Only existing project node /32 addresses; no public ingress.',
                         'Only TCP 8444; preserve application and database rules.']}},
            'Properties': {'GroupId': {'Ref': 'ControlGroup'}, 'IpProtocol': 'tcp',
                           'FromPort': 8444, 'ToPort': 8444, 'CidrIp': {'Ref': key},
                           'Description': 'Private operational log gateway'}}
    body = {'AWSTemplateFormatVersion': '2010-09-09',
            'Description': 'Private log gateway ingress only; remove this stack before foundation network deletion.',
            'Metadata': {'AWSToolsMetrics': {'AWSAgentToolkit': 'aws-cloudformation@3'}},
            'Parameters': parameters, 'Resources': resources}
    return body, {'Node' + str(i): value for i, value in enumerate(addresses, 1)}
