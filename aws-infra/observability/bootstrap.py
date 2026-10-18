"""Approved in-place observability installation. Private JSON input; never log secrets."""
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
CONF = Path('/etc/music-cluster/observability')
DATA = Path('/var/lib/music-cluster/observability')
os.umask(0o077)


@contextmanager
def installation_lock():
    if os.geteuid() != 0:
        raise RuntimeError('root_required')
    with Path('/run/music-observability-install.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def run(args, **kwargs):
    value = subprocess.run(args, capture_output=True, **kwargs)
    if value.returncode:
        raise RuntimeError('command_failed:' + Path(args[0]).name)
    return value.stdout


def write(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(content)
    temporary.chmod(mode)
    temporary.replace(path)


def distribution(product):
    versions = json.loads((HERE / 'versions.json').read_text())
    version = versions['version']
    target = Path('/opt/music-observability') / (product + '-' + version)
    if (target / '.verified').exists():
        return target
    archive = Path('/var/cache') / (product + '-' + version + '-linux-x86_64.tar.gz')
    prefix = 'beats/filebeat' if product == 'filebeat' else product
    url = 'https://artifacts.elastic.co/downloads/' + prefix + '/' + archive.name
    if not archive.exists():
        run(['curl', '--fail', '--silent', '--show-error', '--location', '--retry', '3', '--max-time', '900', '--output', str(archive) + '.partial', url])
        Path(str(archive) + '.partial').replace(archive)
    with archive.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha512').hexdigest()
    if digest != versions[product]['sha512']:
        raise RuntimeError('upstream_checksum_mismatch')
    target.parent.mkdir(exist_ok=True)
    target.parent.chmod(0o755)
    with tarfile.open(archive) as handle:
        root_name = handle.getmembers()[0].name.split('/')[0]
        handle.extractall(target.parent, filter='data')
    extracted = target.parent / root_name
    if extracted != target:
        extracted.rename(target)
    (target / '.verified').touch()
    return target


def es_request(c, method, path, body=None, user='cluster_admin', password=None):
    password = password or c['admin_password']
    headers = {'Authorization': 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode(), 'Content-Type': 'application/json'}
    request = urllib.request.Request('https://' + c['es_hosts'][0] + ':9200' + path,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
    with urllib.request.urlopen(request, context=ssl.create_default_context(cafile=str(CONF / 'ca.crt')), timeout=30) as response:
        return json.load(response)


def setup_elastic(c):
    fields = {'@timestamp': {'type': 'date'}, 'message': {'type': 'text'},
              'host': {'properties': {'name': {'type': 'keyword'}}},
              'event': {'properties': {'dataset': {'type': 'keyword'}, 'outcome': {'type': 'keyword'}, 'id': {'type': 'keyword'}}},
              'service': {'properties': {'name': {'type': 'keyword'}}},
              'log': {'properties': {'level': {'type': 'keyword'}}},
              'ops': {'type': 'object', 'dynamic': True}}
    keywords = ['status','method','stage','source','category','error_type','request_id','job_id','collection','event_type','placement','result','ad_id','service','state','timestamp_basis']
    numeric = ['elapsed_seconds','pipeline_latency_seconds','latency_seconds','events','grids','normalized_rows','http_status','bytes','batch_id','count','pending','stream_records','projected_events','queued_events','acked_events','failed_events','rss_bytes','age_seconds','active','is_test']
    fields['ops']['properties'] = {**{k: {'type': 'keyword'} for k in keywords},
                                   **{k: {'type': 'double'} for k in numeric if k != 'is_test'},
                                   'is_test': {'type': 'boolean'}}
    es_request(c, 'PUT', '/_index_template/ops-mlo-v1', {
        'index_patterns': ['ops-mlo-*'], 'priority': 200,
        'template': {'settings': {'number_of_shards': 1, 'number_of_replicas': 1, 'refresh_interval': '5s'},
                     'mappings': {'dynamic': False, 'properties': fields}},
        '_meta': {'purpose': 'Sanitized operational copies; originals remain authoritative; no automatic deletion.'}})
    es_request(c, 'PUT', '/_security/role/ops_mlo_writer', {
        'cluster': ['monitor'], 'indices': [{'names': ['ops-mlo-*'], 'privileges': ['auto_configure','create_index','create_doc','index','view_index_metadata']}]})
    es_request(c, 'PUT', '/_security/role/ops_mlo_reader', {
        'cluster': [], 'indices': [{'names': ['ops-mlo-*'], 'privileges': ['read','view_index_metadata']}]})
    for name, password, roles in [('ops_ingest', c['writer_password'], ['ops_mlo_writer']),
                                  ('ops_admin', c['viewer_password'], ['kibana_admin','ops_mlo_reader'])]:
        es_request(c, 'PUT', '/_security/user/' + name, {'password': password, 'roles': roles})
        authenticated = es_request(c, 'GET', '/_security/_authenticate', user=name, password=password)
        if authenticated.get('username') != name:
            raise RuntimeError('new_user_authentication_failed')
    token_path = CONF / 'kibana-service-token'
    if not token_path.exists():
        result = es_request(c, 'POST', '/_security/service/elastic/kibana/credential/token/music-observability-v1')
        write(token_path, result['token']['value'])
    return token_path.read_text().strip()


def hub(c):
    runtime = json.loads(Path('/etc/music-cluster/runtime.json').read_text())
    if runtime['node']['name'] != 'control-b':
        raise RuntimeError('control_b_hub_required')
    CONF.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    DATA.chmod(0o751)
    shutil.copyfile('/etc/music-cluster/control/tls/ca.crt', CONF / 'ca.crt')
    token = setup_elastic(c)
    binary = distribution('kibana')
    binary.parent.chmod(0o755)
    run(['chmod','-R','a+rX',str(binary)])
    if subprocess.run(['id', 'music-kibana'], capture_output=True).returncode:
        run(['useradd','--system','--home-dir',str(DATA / 'kibana'),'--shell','/usr/sbin/nologin','music-kibana'])
    (DATA / 'kibana').mkdir(exist_ok=True)
    run(['chown','-R','music-kibana:music-kibana',str(DATA / 'kibana')])
    config = {'server.host': '127.0.0.1', 'server.port': 5601, 'server.basePath': '/ops',
              'server.rewriteBasePath': True, 'server.publicBaseUrl': c['public_url'] + '/ops',
              'server.maxPayload': 1048576, 'elasticsearch.hosts': ['https://' + h + ':9200' for h in c['es_hosts']],
              'elasticsearch.ssl.certificateAuthorities': [str(CONF / 'ca.crt')],
              'elasticsearch.ssl.verificationMode': 'full', 'elasticsearch.serviceAccountToken': token,
              'path.data': str(DATA / 'kibana'), 'xpack.security.secureCookies': True,
              'xpack.security.sameSiteCookies': 'Lax', 'telemetry.enabled': False,
              'xpack.security.encryptionKey': c['encryption_keys'][0],
              'xpack.encryptedSavedObjects.encryptionKey': c['encryption_keys'][1],
              'xpack.reporting.encryptionKey': c['encryption_keys'][2],
              'xpack.reporting.roles.enabled': False,
              'logging.root.level': 'warn'}
    write(CONF / 'kibana.yml', json.dumps(config, indent=2), 0o640)
    run(['chown','root:music-kibana',str(CONF / 'kibana.yml')])
    CONF.chmod(0o751)
    (CONF / 'ca.crt').chmod(0o644)
    write('/etc/systemd/system/music-kibana.service', f'''[Unit]
Description=Music operations Kibana
After=network-online.target
[Service]
User=music-kibana
Group=music-kibana
WorkingDirectory={binary}
Environment=NODE_OPTIONS=--max-old-space-size=1024
Environment=ELASTIC_APM_ACTIVE=false
ExecStart={binary}/bin/kibana --config {CONF}/kibana.yml
Restart=on-failure
RestartSec=15
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
MemoryMax=2G
[Install]
WantedBy=multi-user.target
''', 0o644)
    upstream = '\n'.join(' server ' + h + ':9200 max_fails=2 fail_timeout=10s;' for h in c['es_hosts'])
    write('/etc/nginx/conf.d/music-observability.conf', '''upstream music_ops_elasticsearch {
''' + upstream + '''
 keepalive 8;
}
server {
 listen 8444 ssl;
 server_name _;
 ssl_certificate /etc/music-cluster/control/tls/node.crt;
 ssl_certificate_key /etc/music-cluster/control/tls/node.key;
 ssl_protocols TLSv1.2 TLSv1.3;
 client_max_body_size 8m;
 access_log off;
 location /elastic/ {
  proxy_pass https://music_ops_elasticsearch/;
  proxy_ssl_verify on;
  proxy_ssl_trusted_certificate /etc/music-cluster/observability/ca.crt;
  proxy_ssl_name es-01;
  proxy_ssl_server_name on;
  proxy_http_version 1.1;
  proxy_set_header Connection "";
 }
 location /ops/ {
  proxy_pass http://127.0.0.1:5601;
  proxy_http_version 1.1;
  proxy_set_header Host ''' + c['public_host'] + ''';
  proxy_set_header X-Forwarded-Proto https;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_read_timeout 120s;
 }
 location / { return 404; }
}
''', 0o640)
    # Each upstream certificate has a different IP SAN; pin ES01 for verification.
    # HA endpoint verification is configured per server by using the shared DNS SAN only if available.
    # Current cluster certificate SAN is node-specific, so use a verified single ES endpoint.
    p = Path('/etc/nginx/conf.d/music-observability.conf')
    value = p.read_text()
    value = value.replace(upstream, ' server ' + c['es_hosts'][0] + ':9200;')
    write(p, value, 0o640)
    run(['nginx','-t'])
    run(['systemctl','daemon-reload'])
    run(['systemctl','enable','--now','music-kibana'])
    run(['systemctl','reload','nginx'])
    print(json.dumps({'hub_installed': True, 'version': '8.19.23', 'credentials_in_output': False}))


def public_route(c):
    CONF.mkdir(parents=True, exist_ok=True)
    route = '''location = /ops {
 absolute_redirect off;
 return 302 /ops/;
}
location ^~ /ops/ {
 proxy_pass https://''' + c['hub_ip'] + ''':8444;
 proxy_ssl_verify on;
 proxy_ssl_trusted_certificate /etc/music-cluster/control/tls/ca.crt;
 proxy_ssl_name control-b;
 proxy_ssl_server_name on;
 proxy_http_version 1.1;
 proxy_set_header Host ''' + c['public_host'] + ''';
 proxy_set_header X-Forwarded-Proto https;
 proxy_set_header Upgrade $http_upgrade;
 proxy_set_header Connection "upgrade";
 proxy_read_timeout 120s;
 add_header Cache-Control "no-store" always;
}
'''
    write('/etc/nginx/music-ops-public.locations', route, 0o640)
    path = Path('/etc/nginx/sites-enabled/music-app').resolve()
    original = path.read_text()
    anchor = '    location = /health/'
    include = '    include /etc/nginx/music-ops-public*.locations;\n'
    if include not in original:
        if original.count(anchor) != 1:
            raise RuntimeError('public_nginx_anchor_mismatch')
        backup = CONF / 'nginx-before-ops.conf'
        if not backup.exists():
            write(backup, original)
        write(path, original.replace(anchor, include + anchor), 0o640)
    try:
        run(['nginx','-t'])
        run(['systemctl','reload','nginx'])
    except Exception:
        write(path, original, 0o640)
        raise
    print(json.dumps({'public_ops_route_installed':True,'app_restart':False}))


if __name__ == '__main__':
    c = json.loads(Path(sys.argv[2]).read_text())
    with installation_lock():
        if sys.argv[1] == 'hub':
            hub(c)
        elif sys.argv[1] == 'public':
            public_route(c)
