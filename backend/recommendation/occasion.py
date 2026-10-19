"""Read an immutable occasion sidecar for the explicitly local CSV preview."""
import csv
import hashlib
import json
from pathlib import Path

STATUSES = {'GENERAL', 'SEASONAL_EVENT', 'REVIEW_REQUIRED', 'UNSCREENED'}
SOURCES = {'RULE_SCREEN', 'APPROVED_RULE', 'HUMAN_REVIEW'}


def general_eligible(track):
    """Missing or unversioned decisions never enter general recommendation candidates."""
    return (track.get('occasion_status')=='GENERAL'
            and isinstance(track.get('decision_source'),str) and track['decision_source'] in SOURCES
            and all(isinstance(track.get(field),str) and bool(track[field].strip())
                    for field in ('occasion_policy_version','occasion_decision_version')))


def load_occasion_decisions(directory, source_sha256):
    """Return screened decisions only after manifest/source/artifact checks."""
    root = Path(directory)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    path = root / 'occasion_decisions.csv'
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if (manifest.get('schema_version') != 'GENERAL_CANDIDATES_MANIFEST_V1'
            or manifest.get('source_dataset_sha256') != source_sha256
            or manifest.get('artifacts', {}).get('occasion_decisions.csv') != digest
            or not manifest.get('occasion_policy_version')):
        raise ValueError('Occasion manifest source or artifact verification failed')
    decisions = {}
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            track_id = row.get('track_id', '')
            if (not track_id or track_id in decisions or row.get('occasion_status') not in STATUSES
                    or row.get('decision_source') not in SOURCES
                    or row.get('occasion_policy_version') != manifest['occasion_policy_version']
                    or not row.get('occasion_decision_version')):
                raise ValueError('Invalid, duplicate or unversioned occasion decision')
            decisions[track_id] = {name: row[name] for name in (
                'occasion_status', 'decision_source', 'occasion_policy_version', 'occasion_decision_version')}
    if not decisions:
        raise ValueError('Occasion decisions must not be empty')
    return decisions, digest, manifest['occasion_policy_version']
