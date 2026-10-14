#!/usr/bin/env python3
"""Create a local CA and node SAN certificates; retain all existing identities."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from config import load, write_private


def run(*args):
    r = subprocess.run(['openssl', *args], capture_output=True, text=True)
    if r.returncode: raise ValueError('OpenSSL operation failed: ' + args[0])


def prepare(config, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    ca_key, ca_cert = directory / 'ca.key', directory / 'ca.crt'
    if ca_key.exists() != ca_cert.exists():
        raise ValueError('Partial CA exists; preserve it and inspect before continuing')
    if not ca_key.exists():
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp) / 'ca.cnf'
            cfg.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ca_ext\nprompt=no\n[dn]\nCN=Music cluster AWS CA\n[ca_ext]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n')
            run('req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-sha256', '-days', '365',
                '-config', str(cfg), '-keyout', str(ca_key), '-out', str(ca_cert))
    run('x509', '-in', str(ca_cert), '-checkend', '604800', '-noout')
    for node in config['inventory']['nodes']:
        target = directory / node['name']; target.mkdir(exist_ok=True); target.chmod(0o700)
        identity = {'name': node['name'], 'address': node['address'], 'environment': config['env']['ENVIRONMENT']}
        loopback = bool(set(node.get('roles', [])) & {'postgresql', 'mongodb'})
        if loopback: identity['loopback_san'] = True
        marker = target / 'identity.json'
        if marker.exists():
            if json.loads(marker.read_text()) != identity:
                raise ValueError('Certificate SAN inventory changed: ' + node['name'] + '; explicit rotation required')
            if not (target / 'node.key').exists() or not (target / 'node.crt').exists():
                raise ValueError('Partial node certificate; inspect before retry')
            run('verify', '-CAfile', str(ca_cert), str(target / 'node.crt'))
            run('x509', '-in', str(target / 'node.crt'), '-checkend', '604800', '-noout')
            continue
        if any(target.iterdir()): raise ValueError('Partial node PKI directory: ' + node['name'])
        with tempfile.TemporaryDirectory() as temp:
            csr = Path(temp) / 'node.csr'; cfg = Path(temp) / 'node.cnf'
            cfg.write_text('[req]\ndistinguished_name=dn\nprompt=no\n[dn]\nCN=' + node['name'] + '\n[node_ext]\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth,clientAuth\nsubjectAltName=DNS:' + node['name'] + ',IP:' + node['address'] + (',DNS:localhost,IP:127.0.0.1' if loopback else '') + '\n')
            run('req', '-new', '-newkey', 'rsa:3072', '-nodes', '-sha256', '-config', str(cfg),
                '-keyout', str(target / 'node.key'), '-out', str(csr))
            run('x509', '-req', '-in', str(csr), '-CA', str(ca_cert), '-CAkey', str(ca_key),
                '-set_serial', '0x' + secrets.token_hex(16), '-days', '365', '-sha256',
                '-extfile', str(cfg), '-extensions', 'node_ext', '-out', str(target / 'node.crt'))
        write_private(marker, json.dumps(identity) + '\n')
    for path in directory.rglob('*'):
        if path.is_file(): path.chmod(0o600)
    print('PKI ready; CA private key remains on the administrator Mac and is never bundled.')


if __name__ == '__main__':
    os.umask(0o077)
    p = argparse.ArgumentParser()
    p.add_argument('--env', required=True); p.add_argument('--inventory', required=True); p.add_argument('--output', required=True)
    a = p.parse_args()
    try:
        prepare(load(a.env, a.inventory, stage='preflight'), a.output)
    except (ValueError, OSError, KeyError) as e:
        print('[FAIL] ' + str(e), file=sys.stderr); sys.exit(1)
