"""Offline route/ingress and application handoff gaps, never live AWS proof."""
import ipaddress
from templates import ingress_sources
from application_validation import input_issues, FIELDS


def route(c, source_name, target_name, port):
    nodes = {n['name']: dict(n, profile=a['profile']) for a in c['accounts'] for n in a['nodes']}
    source, target = nodes[source_name], nodes[target_name]
    same_vpc = source['profile'] == target['profile']
    peer = same_vpc or any(set(p) == {source['profile'], target['profile']} for p in c['peering_pairs'])
    ingress = any(r['IpProtocol'] == 'tcp' and r['FromPort'] <= port <= r['ToPort']
                  and ipaddress.ip_address(source['private_ip']) in ipaddress.ip_network(r['CidrIp'])
                  for r in ingress_sources(c, target))
    return {'source': source_name, 'target': target_name, 'port': port, 'direct_route_designed': peer,
            'destination_ingress_designed': ingress, 'design_path_available': peer and ingress,
            'live_connectivity_verified': False}


def plan(c, contract):
    if not isinstance(contract,dict) or type(contract.get('schema_version')) is not int or contract['schema_version'] != 1:
        raise ValueError('Application contract schema 1 required')
    invalid,unsafe=input_issues(contract,c)
    if any(not isinstance(contract.get(section),dict) for section in FIELDS):
        return {'mode':'offline input validation; no AWS calls','missing_contract_fields':[], 'blocked_choices':[],
                'invalid_contract_fields':invalid,'unsafe_input_fields':unsafe,'contract_inputs_complete':False,
                'application_or_ha_verified':False,'business_application_source_required_for_infrastructure':False}
    nodes = [n for a in c['accounts'] for n in a['nodes']]
    mongo = next(n for n in nodes if n['role'] == 'mongodb')
    port = c['service_ports']['mongodb']
    sources = [n for n in nodes if n['role'] in ('control', 'spark', 'advertising')]
    matrix = [route(c, n['name'], mongo['name'], port) for n in sources]
    gaps = [];blocked = []
    weather = contract['weather_mongodb'];writer = weather.get('writer_node')
    if writer is None:
        gaps.append('weather_mongodb.writer_node: choose the execution host/process; Driver and executors differ')
    else:
        selected = [n['name'] for n in sources if n['role']=='control'] if writer=='active-control' else [writer]
        matching = [r for r in matrix if r['source'] in selected]
        if len(matching)!=len(selected) or not matching or not all(r['design_path_available'] for r in matching):
            blocked.append('weather_mongodb.writer_node: approved direct route and destination ingress are required')
    for key in ('database', 'username', 'auth_source'):
        value = weather.get(key)
        if value is None:
            gaps.append('weather_mongodb.' + key)
        elif value in ('advertising', 'advertising_app', 'admin', 'local', 'config', 'root'):
            blocked.append('weather_mongodb.' + key + ': dedicated weather scope required')
    if weather.get('database') and weather.get('auth_source') and weather['database'] != weather['auth_source']:
        blocked.append('weather_mongodb.auth_source: this proposed dedicated-user contract uses the weather database')
    if weather.get('privileges') != ['readWrite'] or weather.get('tls') is not True or weather.get('verify_hostname') is not True:
        blocked.append('weather_mongodb: preserve database-only privileges and verified TLS')
    for section, fields in {
        'weather_mongodb': ('writer_process', 'credential_reference'),
        'elasticsearch': ('application_transport', 'writer_execution', 'document_id_rule', 'ordering_rule', 'failure_retry_rule', 'credential_reference'),
        'web': ('asgi_program', 'asgi_version', 'entrypoint', 'workers', 'start_argv', 'stop_timeout_seconds', 'working_directory','dependency_lock_reference','dependency_lock_sha256'),
        'single_active': ('supervised_argv', 'driver_application_identity', 'query_key', 'checkpoint_reference', 'stop_evidence','working_directory'),
    }.items():
        for field in fields:
            if contract[section].get(field) in (None, '', []):
                gaps.append(section + '.' + field)
    if contract['web'].get('port') != 8000 or contract['web'].get('health_path') != '/health/':
        blocked.append('web: changing the existing port/health contract requires coordinated configuration review')
    return {'mode': 'offline design and handoff; no AWS calls or configuration changes',
            'weather_mongodb_routes': matrix, 'missing_contract_fields': gaps, 'blocked_choices': blocked,
            'invalid_contract_fields':invalid,'unsafe_input_fields':unsafe,
            'contract_inputs_complete': not gaps and not blocked and not invalid and not unsafe, 'application_or_ha_verified': False,
            'business_application_source_required_for_infrastructure': False,
            'es_infrastructure_probe_transport': 'HTTPS REST/Bulk without an ES Spark JAR',
            'application_es_transport_selected': contract['elasticsearch'].get('application_transport') if not invalid and not unsafe else None,
            'automatic_network_or_database_changes': False}
