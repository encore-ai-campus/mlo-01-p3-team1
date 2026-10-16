"""Data-only native DB configuration. Credentials never enter units or command arguments."""
import ipaddress
import json
import re

SECRET_KEYS = ('POSTGRES_APP_PASSWORD', 'MONGO_ADMIN_PASSWORD', 'MONGO_APP_PASSWORD')
KINDS = {'postgresql', 'mongodb'}


def validate(c):
    kind = c['node']['role']
    if kind not in KINDS or c['env'].get('ENVIRONMENT') != 'aws' or not c['aws'].get('generation'):
        raise ValueError('Native database requires an AWS database node/generation')
    address = ipaddress.ip_address(c['node']['address'])
    if address.version != 4 or not address.is_private or address.is_loopback:
        raise ValueError('Database requires private IPv4')
    d = c['database']
    if kind=='postgresql' and d.get('major')!=16 or kind=='mongodb' and d.get('series')!='8.0':
        raise ValueError('Database series must match the supported package lock')
    for field in ('database', 'user') + (('admin_user',) if kind == 'mongodb' else ()):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', d.get(field, '')):
            raise ValueError('Invalid database identifier: ' + field)
    if kind=='postgresql' and (d['user'] in ('all','postgres','replication') or d['database'] in ('all','sameuser','samerole','samegroup','replication')):
        raise ValueError('Reserved PostgreSQL HBA/admin identifiers are forbidden')
    if kind=='mongodb' and (d['database'] in ('admin','local','config') or d['user']==d['admin_user']):
        raise ValueError('MongoDB app database/user must be separate from admin')
    if type(d['port']) is not int or not 1 <= d['port'] <= 65535:
        raise ValueError('Invalid database port')
    keys = ('POSTGRES_APP_PASSWORD',) if kind == 'postgresql' else SECRET_KEYS[1:]
    for key in keys:
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,}', c['env'].get(key, '')):
            raise ValueError('Database secret is missing or invalid: ' + key)
    for client in d['clients']:
        ip = ipaddress.ip_address(client)
        if ip.version != 4 or not ip.is_private or ip.is_loopback:
            raise ValueError('Invalid database client address')
    if not d['clients']:
        raise ValueError('Explicit database client allowlist required')
    lock = c['database_versions'][kind]
    expected = {'postgresql-16', 'postgresql-client-16'} if kind == 'postgresql' else {'mongodb-org-server', 'mongodb-mongosh'}
    if {p['name'] for p in lock['packages']} != expected:
        raise ValueError('Database package lock must include server and client')
    for p in lock['packages']:
        if not re.fullmatch(r'[0-9A-Za-z.+:~_-]+', p['version']) or not re.fullmatch(r'[0-9a-f]{64}', p['sha256']):
            raise ValueError('Invalid database package version/hash')
        if not re.fullmatch(r'[A-Za-z0-9.+%:~_-]+\.deb', p['filename']):
            raise ValueError('Invalid database package filename')
    if kind == 'postgresql' and any(not p['version'].startswith('16.') for p in lock['packages']):
        raise ValueError('PostgreSQL 16 is the selected baseline')
    if kind == 'mongodb' and not next(p['version'] for p in lock['packages'] if p['name'] == 'mongodb-org-server').startswith('8.0.'):
        raise ValueError('MongoDB 8.0 is the selected baseline')
    return kind


def runtime(c, inventory_node, env, versions):
    kind = inventory_node['role']
    definition = dict(c['databases'][kind])
    definition['port'] = c['service_ports'][kind]
    client_role = 'control' if kind == 'postgresql' else 'advertising'
    definition['clients'] = [n['private_ip'] for a in c['accounts'] for n in a['nodes'] if n['role'] == client_role]
    keys = ('POSTGRES_APP_PASSWORD',) if kind == 'postgresql' else SECRET_KEYS[1:]
    value = {'aws': {k: c[k] for k in ('project', 'environment', 'generation')},
             'node': {**inventory_node, 'address': inventory_node['private_ip'], 'roles': [kind]},
             'env': {'ENVIRONMENT': 'aws', 'AWS_REGION': c['region'], **{k: env[k] for k in keys}},
             'database': definition, 'database_versions': versions}
    validate(value)
    return value


def client(c, env, kind):
    server = next(n for a in c['accounts'] for n in a['nodes'] if n['role'] == kind)
    definition = c['databases'][kind]
    key = 'POSTGRES_APP_PASSWORD' if kind == 'postgresql' else 'MONGO_APP_PASSWORD'
    return {'kind': kind, 'host': server['private_ip'], 'port': c['service_ports'][kind],
            'database': definition['database'], 'user': definition['user'], 'password': env[key]}


def client_environment(c):
    d = c['database_client']
    for field in ('database', 'user'):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', d[field]):
            raise ValueError('Invalid client database identifier')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,}', d['password']):
        raise ValueError('Invalid client database credential')
    ip = ipaddress.ip_address(d['host'])
    if ip.version != 4 or not ip.is_private or ip.is_loopback or type(d['port']) is not int or not 1 <= d['port'] <= 65535:
        raise ValueError('Invalid database client endpoint')
    if d['kind'] == 'postgresql' and c['node']['role'] == 'control':
        values = {'POSTGRES_HOST': d['host'], 'POSTGRES_PORT': d['port'], 'POSTGRES_DB': d['database'],
                  'POSTGRES_USER': d['user'], 'POSTGRES_PASSWORD': d['password'], 'POSTGRES_SSLMODE': 'verify-full',
                  'POSTGRES_SSLROOTCERT': '/etc/music-cluster/control/tls/ca.crt'}
    elif d['kind'] == 'mongodb' and c['node']['role'] == 'advertising':
        values = {'MONGO_HOST': d['host'], 'MONGO_PORT': d['port'], 'MONGO_DATABASE': d['database'],
                  'MONGO_USER': d['user'], 'MONGO_PASSWORD': d['password'], 'MONGO_AUTH_SOURCE': d['database'],
                  'MONGO_TLS': 'true', 'MONGO_TLS_CA_FILE': '/etc/music-cluster/advertising/tls/ca.crt'}
    else:
        raise ValueError('Database client role mismatch')
    return ''.join(k + '=' + str(v) + '\n' for k, v in values.items())


def postgres_files(c):
    assert validate(c) == 'postgresql'
    d = c['database']
    conf = f"""listen_addresses = '127.0.0.1,{c['node']['address']}'
port = {d['port']}
data_directory = '/var/lib/music-cluster/postgresql/data'
hba_file = '/etc/music-cluster/postgresql/pg_hba.conf'
unix_socket_directories = '/run/music-postgresql'
password_encryption = 'scram-sha-256'
ssl = on
ssl_cert_file = '/etc/music-cluster/postgresql/tls/node.crt'
ssl_key_file = '/etc/music-cluster/postgresql/tls/node.key'
ssl_min_protocol_version = 'TLSv1.2'
max_connections = 50
shared_buffers = '128MB'
work_mem = '4MB'
log_statement = 'none'
log_min_error_statement = 'panic'
log_parameter_max_length_on_error = 0
"""
    hba = 'local all postgres peer\nlocal all all reject\n'
    for ip in ['127.0.0.1', *d['clients']]:
        hba += f"hostssl {d['database']} {d['user']} {ip}/32 scram-sha-256\n"
    hba += 'host all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n'
    return {'postgresql.conf': conf, 'pg_hba.conf': hba}


def mongo_config(c, loopback_only=False):
    assert validate(c) == 'mongodb'
    # JSON is a YAML subset accepted by mongod; prevents YAML injection.
    return json.dumps({'storage': {'dbPath': '/var/lib/music-cluster/mongodb/data',
                                  'wiredTiger': {'engineConfig': {'cacheSizeGB': 0.5}}},
                       'net': {'port': c['database']['port'],
                               'bindIp': '127.0.0.1' if loopback_only else '127.0.0.1,' + c['node']['address'],
                               'tls': {'mode': 'requireTLS', 'certificateKeyFile': '/etc/music-cluster/mongodb/tls/server.pem',
                                       'CAFile': '/etc/music-cluster/mongodb/tls/ca.crt',
                                       'allowConnectionsWithoutCertificates': True, 'disabledProtocols': 'TLS1_0,TLS1_1'}},
                       'security': {'authorization': 'enabled'}, 'systemLog': {'destination': 'file',
                       'path': '/var/lib/music-cluster/mongodb/mongod.log', 'logAppend': True}}, indent=2) + '\n'


def unit(kind):
    if kind not in KINDS:
        raise ValueError('Unsupported database service')
    user = 'postgres' if kind == 'postgresql' else 'mongodb'
    command = '/usr/lib/postgresql/16/bin/postgres -D /var/lib/music-cluster/postgresql/data -c config_file=/etc/music-cluster/postgresql/postgresql.conf' if kind == 'postgresql' else '/usr/bin/mongod --config /etc/music-cluster/mongodb/mongod.conf'
    return f"""[Unit]
Description=Music AWS {kind}
After=network-online.target
Wants=network-online.target
RequiresMountsFor=/var/lib/music-cluster/{kind}
[Service]
Type=simple
User={user}
Group={user}
RuntimeDirectory=music-{kind}
RuntimeDirectoryMode=0750
ExecStart={command}
Restart=on-failure
RestartSec=5
TimeoutStopSec=120
KillSignal={'SIGINT' if kind == 'postgresql' else 'SIGTERM'}
LimitNOFILE=64000
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/music-cluster/{kind} /run/music-{kind}
[Install]
WantedBy=multi-user.target
"""
