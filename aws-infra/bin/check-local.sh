#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
python3 bin/infra.py --config config/project.example.json render
python3 bin/check-public.py
${AWS_INFRA_CFN_LINT:-.tools/validation/bin/cfn-lint} -t templates/*.json -r ap-northeast-2 -f json
${AWS_INFRA_CFN_GUARD:-.tools/cfn-guard} validate --rules tests/project.guard --data templates --output-format json
python3 -m unittest discover -s tests -v
for script in installer/*.sh installer/core/*.sh installer/core/lib/*.sh; do bash -n "$script"; done
