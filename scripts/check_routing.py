"""Check declared routing ownership with the bundled AST auditor; no document/source writes."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from audit_routing import audit


def check(repo):
    scopes=json.loads((repo/'config/routing-scopes.json').read_text(encoding='utf-8'))
    results=[]
    for directory, prefixes in scopes.items():
        report,_=audit(SimpleNamespace(repo=str(repo),routing_dir=directory,base=None,include_all=True,doc_suffix='.md'))
        def owned(path):return any(path==prefix or path.startswith(prefix.rstrip('/')+'/') for prefix in prefixes)
        files=[entry for entry in report['python_files'] if owned(entry['path'])]
        issues=[issue for issue in report['issues'] if owned(issue['path'])]
        for prefix in prefixes:
            if not (repo/prefix).exists():issues.append({'code':'missing_scoped_source','path':prefix})
        results.append({'routing_dir':directory,'python_files':len(files),
            'symbols':sum(len(entry['symbols']) for entry in files),'issues':issues,'ok':not issues})
    return {'scopes':results,'ok':all(result['ok'] for result in results)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    report=check(args.repo.resolve())
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
