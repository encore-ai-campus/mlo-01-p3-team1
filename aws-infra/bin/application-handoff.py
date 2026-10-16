#!/usr/bin/env python3
"""Create a local private handoff/review bundle; no deployment command exists."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from application_handoff import configuration, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'config/project.json'))
    parser.add_argument('--contract', default=str(ROOT / 'config/application-contract.example.json'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = prepare(configuration(args.config), json.loads(Path(args.contract).read_text()), args.output)
    print(json.dumps({'prepared': True, 'review_artifacts_rendered': result['review_artifacts_rendered'],
                      'missing_inputs': len(result['missing_contract_fields']),
                      'invalid_inputs': len(result['invalid_contract_fields']) + len(result['blocked_choices']),
                      'aws_calls': 0, 'commands_executed': 0, 'application_deployed': False}))
    return 0


if __name__ == '__main__':
    try:raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit('인계 준비를 중단했습니다. 입력 형식·경로를 확인해 주세요 (' + type(error).__name__ + '). 비밀값은 출력하지 않습니다.')
