"""Validate non-secret application inputs without imports/execution of team code."""
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit
from control_fencing import FencingError
from control_runtime import Workload
from project import checkpoint_bucket, checkpoint_prefix

FIELDS = {
    'weather_mongodb': {'writer_node', 'writer_process', 'database', 'username', 'auth_source', 'privileges', 'tls', 'verify_hostname', 'credential_reference'},
    'elasticsearch': {'application_transport', 'writer_execution', 'document_id_rule', 'ordering_rule', 'failure_retry_rule', 'credential_reference'},
    'web': {'asgi_program', 'asgi_version', 'entrypoint', 'workers', 'start_argv', 'stop_timeout_seconds', 'port', 'health_path', 'working_directory', 'dependency_lock_reference', 'dependency_lock_sha256'},
    'single_active': {'supervised_argv', 'driver_application_identity', 'query_key', 'checkpoint_reference', 'stop_evidence', 'working_directory'},
}


def input_issues(contract, c):
    """Return field paths only, including when input contains a credential."""
    issues = [];unsafe = []
    def bad(path, reason):issues.append(path + ': ' + reason)
    def visit(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r'(?i)(password|secret|token|private.?key|access.?key)', str(key)):
                    unsafe.append(path or 'contract')
                known = (not path and key in FIELDS) or key in FIELDS.get(path, ())
                child_path = (path + '.' + str(key) if path else str(key)) if known else path
                visit(item, child_path)
        elif isinstance(value, list):
            for item in value:visit(item, path)
        elif isinstance(value, str):
            if (re.search(r'(?i)(?:password|secret|token|access_key)\s*=', value)
                    or re.search(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b', value)
                    or re.search(r'[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s]+@', value)
                    or 'PRIVATE KEY-----' in value
                    or value.lower() in ('--password', '--secret', '--token', '--access-key')):
                unsafe.append(path or 'contract')
    visit(contract, '')
    if not isinstance(contract, dict):return ['contract: object required'], ['contract']
    if set(contract) - (set(FIELDS) | {'schema_version'}):bad('contract', 'unknown fields are not accepted')
    for section, allowed in FIELDS.items():
        value = contract.get(section)
        if not isinstance(value, dict):bad(section, 'object required');continue
        if set(value) - allowed:bad(section, 'unknown fields are not accepted')
    if issues or unsafe:return issues, sorted(set(unsafe))
    web = contract['web'];active = contract['single_active'];es = contract['elasticsearch'];weather = contract['weather_mongodb']
    for section, names in {
        'weather_mongodb': ('writer_node', 'writer_process', 'database', 'username', 'auth_source', 'credential_reference'),
        'elasticsearch': tuple(FIELDS['elasticsearch']),
        'web': ('asgi_program', 'asgi_version', 'entrypoint', 'working_directory', 'dependency_lock_reference', 'dependency_lock_sha256'),
        'single_active': ('driver_application_identity', 'query_key', 'checkpoint_reference', 'stop_evidence', 'working_directory'),
    }.items():
        for name in names:
            value = contract[section].get(name)
            if value is not None and (not isinstance(value, str) or not value.strip() or any(ord(ch) < 32 for ch in value)):
                bad(section + '.' + name, 'nonempty single-line string required')
    def path(value, field):
        if value is not None and (not isinstance(value, str) or not value.startswith('/') or '..' in PurePosixPath(value).parts or any(ch in value for ch in ('\n', '\r', '\0'))):
            bad(field, 'absolute path without traversal required')
    for section in ('web', 'single_active'):
        value = contract[section].get('working_directory')
        path(value, section + '.working_directory')
        if isinstance(value, str) and value != '/opt/music-apps/control' and not value.startswith('/opt/music-apps/control/'):
            bad(section + '.working_directory', 'use the Control application directory')
    path(web.get('dependency_lock_reference'), 'web.dependency_lock_reference')
    lock = web.get('dependency_lock_sha256')
    if lock is not None and (not isinstance(lock, str) or not re.fullmatch(r'[0-9a-f]{64}', lock)):
        bad('web.dependency_lock_sha256', 'exact SHA256 required')
    for field in ('workers', 'stop_timeout_seconds'):
        if web.get(field) is not None and (type(web[field]) is not int or web[field] < 1):bad('web.' + field, 'positive integer required')
    if web.get('asgi_version') is not None and (not isinstance(web['asgi_version'], str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}(?:[a-zA-Z0-9.+-]+)?', web['asgi_version'])):
        bad('web.asgi_version', 'pin an exact version without ranges or wildcards')
    if web.get('entrypoint') is not None and (not isinstance(web['entrypoint'], str) or not re.fullmatch(r'[A-Za-z_]\w*(?:\.\w+)*:[A-Za-z_]\w*(?:\.\w+)*', web['entrypoint'])):
        bad('web.entrypoint', 'ASGI module:attribute required')
    for section, field in (('web', 'start_argv'), ('single_active', 'supervised_argv')):
        argv = contract[section].get(field)
        if argv is None:continue
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a and not any(ord(ch) < 32 for ch in a) for a in argv):
            bad(section + '.' + field, 'structured foreground argv required');continue
        try:Workload(tuple(argv), contract[section].get('working_directory') or '/opt/music-apps/control')
        except (FencingError,TypeError,ValueError):bad(section + '.' + field, 'shell, relative executable or detached Driver is forbidden');continue
        wrappers = ('env', 'nohup', 'setsid', 'systemd-run', 'daemonize')
        detached = ('--daemon', '--daemonize', '--background', '--reload', '--supervise')
        if PurePosixPath(argv[0]).name in wrappers or any(a.split('=', 1)[0] in detached for a in argv):
            bad(section + '.' + field, 'no shell wrapper, daemonization, reload or detached supervision')
        if any(a == '0.0.0.0' or a == '::' or a.endswith('=0.0.0.0') for a in argv):bad(section + '.' + field, 'use the Control private bind address')
        if section == 'web' and not any('{CONTROL_PRIVATE_IP}' in a for a in argv):bad('web.start_argv', 'include {CONTROL_PRIVATE_IP} for per-node binding')
        if section == 'single_active' and PurePosixPath(argv[0]).name == 'spark-submit' and '--deploy-mode=client' not in argv:
            if '--deploy-mode' not in argv or argv.index('--deploy-mode') + 1 >= len(argv) or argv[argv.index('--deploy-mode') + 1] != 'client':
                bad('single_active.supervised_argv', 'explicit Spark client deploy mode required')
    for section in ('weather_mongodb', 'elasticsearch'):
        value = contract[section].get('credential_reference')
        path(value, section + '.credential_reference')
        if isinstance(value, str) and (not value.startswith('/etc/music-cluster/control/') or '/runtime.json' in value or '/fencing/' in value):
            bad(section + '.credential_reference', 'reference a service-specific app credential file')
    if weather.get('credential_reference') not in (None, '/etc/music-cluster/control/weather-database.env'):
        bad('weather_mongodb.credential_reference', 'use the prepared weather environment file')
    es_ref = es.get('credential_reference')
    if isinstance(es_ref, str) and (not es_ref.endswith('.env') or PurePosixPath(es_ref).name in ('database.env', 'weather-database.env', 'advertising-database.env')):
        bad('elasticsearch.credential_reference', 'use a separate Elasticsearch application environment file')
    if es.get('application_transport') not in (None, 'rest-bulk', 'official-spark-connector'):
        bad('elasticsearch.application_transport', 'choose rest-bulk or a separately reviewed official connector')
    if es.get('application_transport') == 'official-spark-connector':
        bad('elasticsearch.application_transport', 'compatible Spark4.1/ES8.19 artifact lock needs a separate review')
    if es.get('writer_execution') not in (None, 'control-driver', 'spark-executors'):
        bad('elasticsearch.writer_execution', 'declare the actual Driver or executor execution location')
    query = active.get('query_key');uri = active.get('checkpoint_reference')
    if query is not None and (not isinstance(query, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}', query) or query.startswith('_infra')):
        bad('single_active.query_key', 'dedicated business query key required')
    if uri is not None:
        if not c.get('generation') or not isinstance(query, str) or not isinstance(uri, str):
            bad('single_active.checkpoint_reference', 'resolved installation generation and query are required')
        else:
            expected = 's3a://' + checkpoint_bucket(c) + '/' + checkpoint_prefix(c) + query + '/'
            try:
                parsed = urlsplit(uri);decoded = unquote(parsed.path)
                valid = (uri.startswith(expected) and parsed.scheme == 's3a' and not parsed.query and not parsed.fragment
                         and '..' not in PurePosixPath(decoded).parts and '_infra-tests' not in decoded and '\\' not in uri)
            except ValueError:valid=False
            if not valid:
                bad('single_active.checkpoint_reference', 'use only this generation and query prefix; no reset/test/original-data path')
    return sorted(set(issues)), sorted(set(unsafe))
