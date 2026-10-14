#!/usr/bin/env python3
"""Read-only guest identity, capacity, neighbor and name-resolution checks."""
import json
import ipaddress
from pathlib import Path
import os
import shutil
import socket
import subprocess
import sys


def resolution_kind(node, peer, resolved):
    if resolved == peer['address']:
        return 'match'
    # Ubuntu normally maps its own hostname to 127.0.1.1 in /etc/hosts.
    # The caller already verified the real inventory IPv4 on this guest's NIC.
    if (peer['name'] == node['name'] and peer['address'] == node['address'] and
            ipaddress.ip_address(resolved).is_loopback):
        return 'self-loopback'
    return 'mismatch'


def check(c, skip_peers=False):
    n = c['node']
    if socket.gethostname().split('.')[0] != n['name']:
        raise ValueError('Hostname differs from inventory; verify target identity before installation')
    addresses = json.loads(subprocess.check_output(['ip', '-j', '-4', 'address', 'show']))
    local = {a['local'] for interface in addresses for a in interface.get('addr_info', [])}
    if n['address'] not in local:
        raise ValueError('Inventory IPv4 is not assigned to this guest')
    if os.cpu_count() < n['cpu']:
        raise ValueError('CPU count is below inventory budget')
    ram = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:'))) // 1024
    if ram < n['memory_mib'] * 0.94:
        raise ValueError('RAM is below inventory budget')
    if shutil.disk_usage('/var/lib/music-cluster').free < n['min_free_disk_gib'] * 1024**3:
        raise ValueError('Insufficient free space on /var')
    failures = []
    for peer in ([] if skip_peers else c['inventory']['nodes']):
        try:
            if c['env']['ENVIRONMENT'] == 'local':
                with socket.create_connection((peer['address'], 22), timeout=3): pass
            else:
                subprocess.run(['ip', '-4', 'route', 'get', peer['address']], check=True, stdout=subprocess.DEVNULL)
        except OSError:
            failures.append(peer['name'] + ': SSH TCP path unavailable')
        try:
            resolved = socket.gethostbyname(peer['name'])
            kind = resolution_kind(n, peer, resolved)
            if kind == 'self-loopback':
                print('[INFO] Own hostname resolves to loopback; inventory IPv4 is verified on this guest')
            elif kind == 'mismatch':
                failures.append(peer['name'] + ': name resolves to a different IP')
        except OSError:
            # Installation uses verified inventory IPv4; unmanaged DHCP DNS is not mandatory.
            print('[INFO] No peer DNS entry: ' + peer['name'] + '; inventory IPv4 will be used')
    if failures:
        raise ValueError('; '.join(failures))
    if subprocess.call(['swapon', '--noheadings', '--show'], stdout=subprocess.DEVNULL) != 0:
        raise ValueError('Unable to inspect swap')
    peers = '; inter-VM SSH TCP connectivity' if c['env']['ENVIRONMENT'] == 'local' else '; peer routes (service connectivity still needs validation)'
    print('[PASS] Guest identity, IPv4 and CPU/RAM/disk' + ('' if skip_peers else peers))


if __name__ == '__main__':
    try: check(json.loads(Path(sys.argv[1]).read_text()), '--skip-peers' in sys.argv[2:])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        print('[FAIL] ' + str(e), file=sys.stderr); sys.exit(1)
