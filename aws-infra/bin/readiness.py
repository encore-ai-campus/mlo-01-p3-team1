"""Offline preparation evidence. Does not authenticate, call AWS or read past receipts."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from project import blockers, web_port
from revision import source_identity

ROOT = Path(__file__).resolve().parents[1]


def source_checks(root):
    """Verify unchanged upstream files; AWS patches are covered by source_identity."""
    root = Path(root)
    manifest = json.loads((root / 'installer/source-manifest.json').read_text())
    base = (root / 'installer/core').resolve()
    patches = manifest['aws_patches']
    issues, verified = [], 0
    for name, expected in manifest['source_files_sha256'].items():
        file = base / name
        if not file.resolve().is_relative_to(base) or not file.is_file() or file.is_symlink():
            issues.append('installer source missing or unsafe: ' + name)
        elif name not in patches:
            if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
                issues.append('installer upstream hash mismatch: ' + name)
            else:
                verified += 1
    return {'verified_upstream_files': verified, 'reviewed_aws_patch_files': sorted(patches),
            'patch_hash_coverage': 'current implementation source_sha256; upstream hashes are preserved',
            'issues': issues}


def check(c, root=ROOT):
    root = Path(root)
    config = copy.deepcopy(c)
    # Match create's automatic generation policy, without assigning/persisting an ID.
    if config.get('generation') is None:
        config['generation'] = 'automatic-at-create'
    core = blockers(config, 'compute')
    alb = blockers(config, 'alb')
    source = source_checks(root)
    tools = {'aws_cli_on_path': shutil.which('aws') is not None,
             'cfn_lint_present': (root / '.tools/validation/bin/cfn-lint').is_file(),
             'cfn_guard_present': (root / '.tools/cfn-guard').is_file()}
    issues = source['issues'] + ['tool unavailable: ' + k for k, ready in tools.items() if not ready]
    # Never propagate config values, ARNs, account IDs, addresses or past AWS observations.
    return {'observed_at': datetime.now(timezone.utc).isoformat(),
            'mode': 'offline; no AWS authentication, queries, change sets, SSM commands or lifecycle changes',
            'implementation': source_identity(),
            'core_missing_inputs': sorted(set(core)), 'alb_missing_inputs': sorted(set(alb)),
            'local_tools': tools, 'installer_source': source,
            'ready_for_aws_preflight': not core and not alb and not issues,
            'preparation_issues': issues,
            'generation_policy': 'assigned only at create; existing retries/restarts retain their generation',
            'web_port_key': 'web' if 'web' in c['service_ports'] else 'gunicorn (legacy alias)',
            'web_port_configured': web_port(c) is not None,
            'static_validation': 'run check-local.sh separately; tool presence is not validation success',
            'aws_read_verification': 'not performed by this command; prior observations are historical',
            'aws_service_predeployment_validation': 'not performed; requires an authorized change-set stage',
            'aws_deployment': 'not performed', 'service_verification': 'not performed',
            'integration_pending': [
                'Team FastAPI/ASGI version lock and systemd web start/stop/health contract',
                'Single-active Collector/Driver/scheduler lifecycle and fail-closed Control fencing',
                'Kafka/S3A/Delta/Elasticsearch connector compatibility and dependency lock',
                'Actual S3 checkpoint single-writer and restart/takeover verification',
                'Spark weather writer location and direct reachable MongoDB path without changing approved peerings',
                'Weather MongoDB database/authSource/user contract, separate from advertising credentials',
                'Application routes, migrations, data flows and ALB target health',
                'Authorized create/setup/verify/destroy/new-generation recreation evidence'],
            'business_app_source_required_for_infra_preparation': False,
            'resources_created': False}
