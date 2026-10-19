"""Offline integration plan; recorded state is historical, never live proof."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'installer/core/lib'))
import connectors
from project import prefix
from revision import source_identity


def plan(c,bundle,root=ROOT):
    root=Path(root);issues=[];manifest=None
    if bundle is None:
        version=json.loads((root/'installer/core/versions.json').read_text())['spark']['version']
        bundle=root/'.local/connectors'/version
    try:
        manifest,_=connectors.validate_bundle(bundle,reviewed_lock=root/'installer/connectors.lock.json')
    except (OSError,ValueError,KeyError) as error:
        issues.append(type(error).__name__+': connector bundle missing, changed or incompatible')
    nodes=[n for a in c['accounts'] for n in a['nodes']]
    marker=root/'.state/lifecycle'/prefix(c)/'current.json';same=None
    if marker.exists():
        recorded=json.loads(marker.read_text());identity=Path(recorded['run'])/'setup-services/identity.json'
        if identity.exists():same=json.loads(identity.read_text())['source']['source_sha256']==source_identity()['source_sha256']
    return {'mode':'offline preparation; no AWS calls, installation, IAM changes or service activation',
            'implementation':source_identity(),'connector_bundle_verified':manifest is not None,
            'additional_jars':len(manifest['jars']) if manifest else 0,'locked_distribution_jars':len(manifest['distribution_jars']) if manifest else 0,
            'connector_install_targets':[n['name'] for n in nodes if n['role'] in ('spark','control')],
            'bundle_issues':issues,'recorded_setup_source_matches_workspace':same,
            'connector_installation_executed':False,'checkpoint_probe_prepared':True,'actual_s3_checkpoint_resume_verified':False,
            'control_promotion_gate_implemented':True,'live_fencing_controller_implemented':True,
            'live_fencing_controller_installed':False,'physical_control_fencing_verified':False,
            'elasticsearch_connector':'Official compatible Spark connector unresolved; bounded Driver-side HTTPS REST/Bulk probe prepared; application transport unselected',
            'required_before_aws_execution':['Review source/package upgrade while preserving generation, successes, data and all secrets/PKI',
                'Explicitly prepare node payloads with the reviewed connector bundle; reject missing or changed locks',
                'Prevent new application submissions throughout classpath changes; an idle snapshot alone is not an admission lock',
                'Confirm no active Spark application before classpath changes and run isolated Kafka/S3A/checkpoint probes',
                'Review the separate Control fencing IAM/SSM proposal and install disabled canary packages before explicitly testing physical takeover'],
            'ready_for_full_integration':False,'business_application_source_required_for_preparation':False}
