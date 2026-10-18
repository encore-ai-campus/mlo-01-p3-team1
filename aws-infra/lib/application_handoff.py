"""Local review artifacts only: never import, install, enable or run team code."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from application_contract import plan
from project import load, prefix, checkpoint_bucket, checkpoint_prefix

ROOT = Path(__file__).resolve().parents[1]


def configuration(path, root=ROOT):
    path = Path(path);c = load(path)
    if c.get('example_only') is False and not c.get('generation'):
        state = json.loads((Path(root) / '.state/lifecycle' / prefix(c) / 'current.json').read_text())
        if state['state'] != 'ready' or state['source_sha256'] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Use the unchanged ready installation configuration')
        c = load(state['resolved_config'])
    return c


def quoted(value):
    # ExecStart ':' disables environment expansion; %% disables specifiers.
    return '"' + value.replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"') + '"'


def bindings(c):
    nodes = [dict(n, profile=a['profile']) for a in c['accounts'] for n in a['nodes']]
    control = [n for n in nodes if n['role'] == 'control']
    result = {'origin': 'Local resolved configuration and published dependency locks; not fresh AWS observation',
              'snapshot_is_live': False, 'scope': {k: c[k] for k in ('project', 'environment', 'generation')},
              'control_hosts': [{'node': n['name'], 'private_ip': n['private_ip'], 'user': 'control'} for n in control],
              'app_source_directory': '/opt/music-apps/control',
              'prepared_python_venv': '/var/lib/music-cluster/control/venv',
              'postgres_environment': '/etc/music-cluster/control/database.env',
              'weather_environment': '/etc/music-cluster/control/weather-database.env',
              'service_ca': '/etc/music-cluster/control/tls/ca.crt',
              'elasticsearch_urls': ['https://' + n['private_ip'] + ':9200' for n in nodes if n['role'] == 'es'],
              'spark_master': 'spark://' + ','.join(n['private_ip'] + ':7077' for n in nodes if n['role'] == 'spark'),
              'spark_submit': '/opt/music-cluster/spark/bin/spark-submit',
              'spark_client_deploy_mode_required': True,
              'es_app_credential_file_prepared_by_this_tool': False,
              'raw_runtime_or_admin_credentials_are_app_inputs': False}
    result['checkpoint_root'] = 's3a://' + checkpoint_bucket(c) + '/' + checkpoint_prefix(c) if c.get('generation') else None
    delta = ROOT / 'installer/delta.lock.json'
    lock = json.loads(delta.read_text());lock_sha = hashlib.sha256(delta.read_bytes()).hexdigest()
    addon = '/opt/music-cluster/spark-addons/delta/' + lock_sha
    result['delta'] = {'lock_sha256': lock_sha, 'spark_version': lock['spark_version'],
                       'jars': [addon + '/' + item['filename'] for item in lock['jars']],
                       'session_conf': {'spark.sql.extensions': 'io.delta.sql.DeltaSparkSessionExtension',
                                        'spark.sql.catalog.spark_catalog': 'org.apache.spark.sql.delta.catalog.DeltaCatalog'},
                       'automatic_global_enable': False, 'observed_installation_claimed': False}
    return result


def previews(c, contract):
    report = plan(c, contract)
    if not report['contract_inputs_complete'] or not c.get('generation'):
        raise ValueError('Complete valid inputs and a resolved generation are required before unit previews')
    template = (ROOT / 'installer/application-web.service.in').read_text();outputs = {}
    for account in c['accounts']:
        for node in account['nodes']:
            if node['role'] != 'control':continue
            replace = lambda value: value.replace('{CONTROL_PRIVATE_IP}', node['private_ip']).replace('{CHECKPOINT_URI}', contract['single_active']['checkpoint_reference'])
            argv = [replace(v) for v in contract['web']['start_argv']]
            unit = template.replace('@WORKING_DIRECTORY@', quoted(contract['web']['working_directory']))
            unit = unit.replace('@WEB_EXEC_START@', ' '.join(quoted(v) for v in argv))
            unit = unit.replace('@STOP_TIMEOUT_SECONDS@', str(contract['web']['stop_timeout_seconds']))
            outputs[node['name'] + '/music-web.service'] = unit
            patch = {'review_only': True, 'requires_new_business_supervisor_installation_review': True,
                     'original_canary_unit_or_runtime_modified': False,
                     'namespace': {k: c[k] for k in ('project', 'environment', 'generation')},
                     'query': contract['single_active']['query_key'],
                     'checkpoint_reference': contract['single_active']['checkpoint_reference'],
                     'workloads': [{'argv': [replace(v) for v in contract['single_active']['supervised_argv']],
                                    'cwd': contract['single_active']['working_directory']}],
                     'environment_file_references': ['/etc/music-cluster/control/database.env', '/etc/music-cluster/control/weather-database.env'],
                     'epoch_owner_or_checkpoint_initialization': False}
            outputs[node['name'] + '/supervisor-patch.review.json'] = json.dumps(patch, ensure_ascii=False, indent=2) + '\n'
    return outputs


def prepare(c, contract, output, root=ROOT):
    root = Path(root).resolve();output = Path(output)
    report = plan(c, contract)
    if report.get('unsafe_input_fields'):
        raise ValueError('Credential content is forbidden; use private credential file references')
    if not output.resolve().is_relative_to((root / '.state').resolve()) or output.is_symlink():
        raise ValueError('Actual handoff artifacts belong in a new ignored .state directory')
    if output.exists():raise ValueError('Handoff output exists; preserve it and choose a new review directory')
    old_umask = os.umask(0o077)
    try:
        output.mkdir(parents=True, mode=0o700)
        ready = report['contract_inputs_complete'] and bool(c.get('generation'))
        report.update(review_artifacts_rendered=ready, application_deployed=False, service_verified=False,
                      generation_resolved=bool(c.get('generation')), aws_calls=0, commands_executed=0)
        files = {'application-contract.pending.json': json.dumps(contract, ensure_ascii=False, indent=2) + '\n',
                 'infrastructure-bindings.json': json.dumps(bindings(c), ensure_ascii=False, indent=2) + '\n',
                 'plan.json': json.dumps(report, ensure_ascii=False, indent=2) + '\n'}
        if ready:files.update({'review/' + k: v for k, v in previews(c, contract).items()})
        else:files['templates/application-web.service.in'] = (ROOT / 'installer/application-web.service.in').read_text()
        groups = {'weather_mongodb': 'A·INF', 'elasticsearch': 'A·INF', 'web': 'B/C·INF', 'single_active': 'A/B/C·INF'}
        lines = ['# 앱 실행 계약 인계', '', '로컬 준비물입니다. 앱 설치·명령 실행·AWS 변경·새 서비스 검증은 수행하지 않았습니다.', '',
                 '## 담당자가 채울 입력', '']
        for item in report.get('missing_contract_fields', []):lines.append('- ' + groups.get(item.split('.')[0], 'INF') + ': `' + item + '`')
        for item in report.get('invalid_contract_fields', []) + report.get('blocked_choices', []):lines.append('- 수정 필요: `' + item + '`')
        lines += ['', '## 적용 전 연결', '',
                  '- 앱 소스는 기반 인프라 준비의 선행 조건이 아닙니다. ASGI/앱 dependency lock·foreground 명령은 앱 담당자가 제공합니다.',
                  '- 웹은 두 Control에 배치하고 Collector/Driver/스케줄러는 별도 단일 active supervisor가 감독합니다. 웹 worker startup에서 singleton 작업을 시작하지 않습니다.',
                  '- 기존 canary 전용 설치기는 업무 앱을 의도적으로 거부합니다. supervisor patch는 검토안이며 새 업무용 설치/lifecycle 연결과 명시 배포 요청이 필요합니다.',
                  '- ES 앱용 설정/권한을 서비스 사용자에게 별도로 분리해야 합니다. 관리자 비밀값을 포함하는 root runtime을 앱에 전달하지 않습니다.',
                  '- 체크포인트/query는 두 Control에서 같아야 하며 재시작/승계 때 초기화하지 않습니다.',
                  '- 이 도구는 ASGI 서버 선택·단일 writer/업무 HA·ALB 건강 상태를 완료 처리하지 않습니다.']
        files['HANDOFF.md'] = '\n'.join(lines) + '\n'
        for relative, content in files.items():
            path = output / relative;path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open('x') as handle:handle.write(content)
            path.chmod(0o600)
        # Save hashes after all content is written; manifest contains no secrets.
        manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'files': {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in files},
            'aws_calls': 0, 'commands_executed': 0, 'application_deployed': False}
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n');(output / 'manifest.json').chmod(0o600)
        return report
    finally:os.umask(old_umask)
