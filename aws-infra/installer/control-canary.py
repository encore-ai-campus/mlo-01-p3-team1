#!/usr/bin/env python3
"""Foreground local heartbeat for isolated fencing tests; no business/S3 data."""
import argparse
import json
import os
from pathlib import Path
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory', required=True)
args = parser.parse_args()
root = Path(args.directory)
if not root.is_absolute() or root.is_symlink():
    raise SystemExit('Explicit private canary directory required')
root.mkdir(parents=True, exist_ok=True, mode=0o700)
epoch = int(os.environ['MUSIC_CONTROL_EPOCH'])
generation = os.environ['MUSIC_CONTROL_GENERATION']
query = os.environ['MUSIC_CONTROL_QUERY']
sequence = 0
while True:
    value = {'pid': os.getpid(), 'epoch': epoch, 'generation': generation, 'query': query,
             'sequence': sequence, 'observed_at': time.time()}
    temporary = root / ('heartbeat-' + str(epoch) + '.tmp')
    temporary.write_text(json.dumps(value));temporary.chmod(0o600)
    temporary.replace(root / ('heartbeat-' + str(epoch) + '.json'))
    sequence += 1
    time.sleep(0.2)
