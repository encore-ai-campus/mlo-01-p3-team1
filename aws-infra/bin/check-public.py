#!/usr/bin/env python3
"""Inspect publishable files without creating a Git repository or printing secrets."""
import argparse
import fnmatch
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def ignored(relative, rules):
    """Subset used by this repository: globs, root paths, directories, negation."""
    parts = relative.split('/')
    result = False
    for raw in rules:
        raw = raw.strip()
        if not raw or raw.startswith('#'):
            continue
        negate = raw.startswith('!')
        pattern = raw[1:] if negate else raw
        anchored = pattern.startswith('/')
        pattern = pattern.lstrip('/')
        directory = pattern.endswith('/')
        pattern = pattern.rstrip('/')
        if directory:
            match = any(fnmatch.fnmatchcase('/'.join(parts[:i]), pattern) for i in range(1, len(parts))) if anchored or '/' in pattern else any(fnmatch.fnmatchcase(p, pattern) for p in parts[:-1])
        else:
            match = fnmatch.fnmatchcase(relative, pattern) if anchored or '/' in pattern else fnmatch.fnmatchcase(parts[-1], pattern)
        if match:
            result = not negate
    return result


def findings(path, data, local_ids=()):
    checks = (
        ('AWS access key ID', r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
        ('private key', r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----'),
        ('credential assignment', r'(?i)(?:aws_secret_access_key|aws_session_token|aws_access_key_id)\s*[\"\']?\s*[:=]\s*[\"\']?([A-Za-z0-9+/=_-]{20,})'),
        ('literal application secret', r'(?i)(?:password|api_key|secret_key|client_secret|access_token)\s*[\"\']?\s*[:=]\s*[\"\']([A-Za-z0-9+/=_-]{16,})[\"\']'),
        ('personal workstation path', r'/' + 'Users/' + r'[^/\s]+/'),
    )
    issues = []
    for label, pattern in checks:
        for match in re.finditer(pattern, data):
            if match.lastindex and re.fullmatch(r'(?:REPLACE_?ME|CHANGE_?ME|EXAMPLE|PLACEHOLDER|X+|0+)', match.group(1), re.I):
                continue
            issues.append({'path': path, 'line': data.count('\n', 0, match.start()) + 1, 'category': label})
    for account in local_ids:
        match = re.search(r'(?<![0-9])' + re.escape(account) + r'(?![0-9])', data)
        if match:
            issues.append({'path': path, 'line': data.count('\n', 0, match.start()) + 1, 'category': 'local AWS account identifier'})
    return issues


def scan(root, rules, local_ids=None, prefix=''):
    root = Path(root)
    issues, count = [], 0
    local = root / 'config/project.json'
    ids = local_ids if local_ids is not None else ([a['account_id'] for a in json.loads(local.read_text())['accounts']] if local.exists() else [])
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if '.git' in path.relative_to(root).parts or ignored(relative, rules):
            continue
        if path.is_symlink():
            issues.append({'path': prefix+relative, 'category': 'public symlink requires review'})
            continue
        if not path.is_file():
            continue
        count += 1
        try:
            data = path.read_text(encoding='utf-8')
        except UnicodeError:
            issues.append({'path': prefix+relative, 'category': 'binary file requires review'})
            continue
        issues.extend(findings(prefix+relative, data, ids))
    return count, issues


def tracked_private_files(root, rules):
    """Also detect previously tracked private files in an existing parent repository."""
    available = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if available.returncode:
        return []
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '.'], capture_output=True, text=True, check=True)
    return [{'path': p, 'category': 'ignored private file is already tracked'} for p in result.stdout.split('\0') if p and ignored(p, rules)]


def scan_project(root, rules):
    """Scan the infra package plus its shared docs/CI when using the parent layout."""
    root=Path(root).resolve()
    count,issues=scan(root,rules)
    issues.extend(tracked_private_files(root,rules))
    scopes=['aws-infra' if root.name=='aws-infra' else 'infrastructure package']
    if root.name!='aws-infra':return count,issues,scopes
    repository=root.parent
    local=root/'config/project.json'
    ids=[a['account_id'] for a in json.loads(local.read_text())['accounts']] if local.exists() else []
    ignore=repository/'.gitignore'
    common=ignore.read_text().splitlines() if ignore.is_file() else rules
    for relative in ('docs/handoff/infra','.github/workflows'):
        folder=repository/relative
        if not folder.is_dir():continue
        if folder.is_symlink():
            issues.append({'path':relative,'category':'public symlink requires review'})
            continue
        found,extra=scan(folder,common,local_ids=ids,prefix=relative+'/')
        count+=found;issues.extend(extra)
        issues.extend({**v,'path':relative+'/'+v['path']} for v in tracked_private_files(folder,common))
        scopes.append(relative)
    if ignore.is_file():
        count+=1;issues.extend(findings('.gitignore',ignore.read_text(),ids))
        required=('aws-infra/config/project.json','aws-infra/config/team.local.json',
                  'aws-infra/.private/runtime.json','aws-infra/.state/run/config.json',
                  'docs/handoff/infra/.env','docs/handoff/infra/node.key')
        issues.extend({'path':v,'category':'missing root ignore rule'} for v in required if not ignored(v,common))
        scopes.append('repository .gitignore')
    return count,issues,scopes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    rules = (args.root / '.gitignore').read_text().splitlines()
    required = ('config/project.json', '.env', '.env.production', 'nested/.env', '.aws/credentials', '.private/payload.json',
                '.state/run/config.json', '.local/history.json', '.tools/tool', 'node.key', 'payload.tgz')
    uncovered = [p for p in required if not ignored(p, rules)]
    count, issues, scopes = scan_project(args.root, rules)
    issues.extend({'path': p, 'category': 'missing ignore rule'} for p in uncovered)
    print(json.dumps({'public_files_checked': count, 'findings_count': len(issues), 'findings': issues,
                      'scopes': scopes, 'coverage': 'listed scopes and tracked private paths; other repository content and prior Git history are not scanned'}, indent=2))
    return 1 if issues else 0


if __name__ == '__main__':
    sys.exit(main())
