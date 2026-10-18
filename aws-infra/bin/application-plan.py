#!/usr/bin/env python3
"""Report offline service routes and missing non-secret application contract inputs."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from application_contract import plan
from application_handoff import configuration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'config/project.example.json'))
    parser.add_argument('--contract', default=str(ROOT / 'config/application-contract.example.json'))
    args = parser.parse_args()
    report = plan(configuration(args.config), json.loads(Path(args.contract).read_text()))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['contract_inputs_complete'] else 1


if __name__ == '__main__':
    try:raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit('계약 검사를 중단했습니다. 입력 형식·경로를 확인해 주세요 (' + type(error).__name__ + '). 비밀값은 출력하지 않습니다.')
