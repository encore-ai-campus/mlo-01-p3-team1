#!/usr/bin/env python3
"""Read-only readiness barrier before any Spark Worker starts."""
import json
import sys
from pathlib import Path
from urllib.request import urlopen

def verify(states):
    if len(states)!=3 or states.count('ALIVE')!=1 or states.count('STANDBY')!=2:
        raise ValueError('Expected exactly one active and two standby Spark Masters')

if __name__=='__main__':
    c=json.loads(Path(sys.argv[1]).read_text());states=[]
    for n in c['inventory']['nodes']:
        if 'spark' in n['roles']:
            with urlopen('http://'+n['address']+':8080/json/',timeout=10) as r:states.append(json.load(r)['status'])
    verify(states)
    print('[PASS] Spark Master barrier: one active, two standby; Workers and Control HA require separate checks')
