#!/usr/bin/env python3
"""Audit changed Python files against 1:1 routing documents.

The report deliberately contains AST metadata rather than source bodies so an
LLM can use deterministic evidence before opening only mismatched files.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class AuditError(RuntimeError):
    """Raised when the audit cannot produce a trustworthy result."""


@dataclass
class Symbol:
    kind: str
    qualified_name: str
    line: int
    signature: str
    signature_core: str
    return_annotation: str | None = None
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    documented: bool = False


def run_git(repo: Path, *arguments: str, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
        text=not binary,
        encoding=None if binary else "utf-8",
    )
    if completed.returncode != 0:
        stderr = (
            completed.stderr.decode("utf-8", errors="replace")
            if binary
            else completed.stderr
        )
        raise AuditError(stderr.strip() or f"git {' '.join(arguments)} failed")
    return completed.stdout


def nul_paths(payload: bytes) -> set[str]:
    return {
        item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for item in payload.split(b"\0")
        if item
    }


def repository_root(value: str) -> Path:
    requested = Path(value).expanduser().resolve()
    root = run_git(requested, "rev-parse", "--show-toplevel")
    return Path(str(root).strip()).resolve()


def changed_paths(repo: Path, base: str | None, include_all: bool) -> list[str]:
    if include_all:
        tracked = nul_paths(run_git(repo, "ls-files", "-z", binary=True))
        untracked = nul_paths(
            run_git(repo, "ls-files", "--others", "--exclude-standard", "-z", binary=True)
        )
        return sorted(tracked | untracked)

    if base:
        changed = nul_paths(
            run_git(repo, "diff", "--name-only", "-z", base, "--", binary=True)
        )
    else:
        changed = nul_paths(
            run_git(repo, "diff", "--name-only", "-z", "--", binary=True)
        )
        changed |= nul_paths(
            run_git(repo, "diff", "--cached", "--name-only", "-z", "--", binary=True)
        )
    changed |= nul_paths(
        run_git(repo, "ls-files", "--others", "--exclude-standard", "-z", binary=True)
    )
    return sorted(changed)


def select_routing_dir(repo: Path, value: str | None) -> Path:
    if value:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = repo / candidate
        candidate = candidate.resolve()
        if not (candidate / "README.md").is_file() or not (candidate / "files").is_dir():
            raise AuditError(f"routing directory is incomplete: {candidate}")
        return candidate

    candidates = sorted(
        path.resolve()
        for path in (repo / "docs").glob("*-routing")
        if (path / "README.md").is_file() and (path / "files").is_dir()
    )
    if len(candidates) != 1:
        names = ", ".join(str(path) for path in candidates) or "none"
        raise AuditError(
            "--routing-dir is required when auto-discovery does not find exactly "
            f"one directory (found: {names})"
        )
    return candidates[0]


def expression(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node).replace("\n", " ")
    except Exception:
        return "<unparseable>"


def decorator_names(nodes: list[ast.expr]) -> list[str]:
    return [expression(node) or "<unknown>" for node in nodes]


def function_symbol(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    owner: str | None = None,
) -> Symbol:
    qualified = f"{owner}.{node.name}" if owner else node.name
    parameters = expression(node.args) or ""
    core = f"{qualified}({parameters})"
    returns = expression(node.returns)
    signature = f"{core} -> {returns}" if returns else core
    return Symbol(
        kind="async_method" if owner and isinstance(node, ast.AsyncFunctionDef)
        else "method" if owner
        else "async_function" if isinstance(node, ast.AsyncFunctionDef)
        else "function",
        qualified_name=qualified,
        line=node.lineno,
        signature=signature,
        signature_core=core,
        return_annotation=returns,
        decorators=decorator_names(node.decorator_list),
    )


def extract_symbols(path: Path) -> tuple[list[Symbol], str | None]:
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        return [], f"{type(exc).__name__}: {exc}"

    symbols: list[Symbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(function_symbol(node))
            continue
        if isinstance(node, ast.ClassDef):
            bases = [expression(base) or "<unknown>" for base in node.bases]
            keywords = [
                f"{item.arg}={expression(item.value)}" for item in node.keywords
            ]
            declaration = ", ".join(bases + keywords)
            symbols.append(Symbol(
                kind="class",
                qualified_name=node.name,
                line=node.lineno,
                signature=f"class {node.name}({declaration})" if declaration else f"class {node.name}",
                signature_core=node.name,
                decorators=decorator_names(node.decorator_list),
                bases=bases,
            ))
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(function_symbol(member, node.name))
    return symbols, None


def compact(value: str) -> str:
    return re.sub(r"[\s`]", "", value)


def mark_documented(symbols: list[Symbol], document: str) -> list[str]:
    normalized = compact(document)
    missing: list[str] = []
    for symbol in symbols:
        expected = symbol.signature if symbol.return_annotation else symbol.signature_core
        if symbol.kind == "class":
            symbol.documented = compact(symbol.qualified_name) in normalized
        else:
            symbol.documented = compact(expected) in normalized
        if not symbol.documented:
            missing.append(expected)
    return missing


def relative_display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def audit(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    repo = repository_root(args.repo)
    routing_dir = select_routing_dir(repo, args.routing_dir)
    paths = changed_paths(repo, args.base, args.include_all)
    status_lines = str(run_git(repo, "status", "--short")).splitlines()
    try:
        head = str(run_git(repo, "log", "-1", "--oneline")).strip()
    except AuditError as exc:
        if "does not have any commits" not in str(exc):
            raise
        head = "(no commits)"
    index_path = routing_dir / "README.md"
    index_text = index_path.read_text(encoding="utf-8-sig")

    python_results: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for relative in (item for item in paths if item.lower().endswith(".py")):
        source_path = repo / Path(relative)
        document_path = routing_dir / "files" / f"{relative}{args.doc_suffix}"
        indexed = relative in index_text
        exists = source_path.is_file()
        document_exists = document_path.is_file()
        entry: dict[str, Any] = {
            "path": relative,
            "state": "present" if exists else "deleted",
            "document": relative_display(document_path, repo),
            "document_exists": document_exists,
            "indexed": indexed,
            "symbols": [],
            "missing_signatures": [],
            "parse_error": None,
        }

        if not exists:
            if document_exists:
                issues.append({"code": "deleted_source_has_document", "path": relative})
            if indexed:
                issues.append({"code": "deleted_source_is_indexed", "path": relative})
            python_results.append(entry)
            continue

        symbols, parse_error = extract_symbols(source_path)
        entry["symbols"] = [asdict(symbol) for symbol in symbols]
        entry["parse_error"] = parse_error
        if parse_error:
            issues.append({"code": "parse_error", "path": relative, "detail": parse_error})
        if not document_exists:
            issues.append({"code": "missing_document", "path": relative})
        else:
            document = document_path.read_text(encoding="utf-8-sig")
            missing = mark_documented(symbols, document)
            entry["missing_signatures"] = missing
            entry["symbols"] = [asdict(symbol) for symbol in symbols]
            for signature in missing:
                issues.append({
                    "code": "missing_signature",
                    "path": relative,
                    "detail": signature,
                })
        if not indexed:
            issues.append({"code": "missing_index", "path": relative})
        python_results.append(entry)

    report: dict[str, Any] = {
        "schema_version": 1,
        "repository": str(repo),
        "git_head": head,
        "git_status": status_lines,
        "routing_dir": relative_display(routing_dir, repo),
        "scope": "all" if args.include_all else f"base:{args.base}" if args.base else "working_tree",
        "changed_paths": paths,
        "python_files": python_results,
        "issues": issues,
        "summary": {
            "changed_path_count": len(paths),
            "python_file_count": len(python_results),
            "symbol_count": sum(len(item["symbols"]) for item in python_results),
            "issue_count": len(issues),
            "ok": not issues,
        },
    }
    return report, 0 if not issues else 1


def text_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"repository: {report['repository']}",
        f"git_head: {report['git_head']}",
        f"routing_dir: {report['routing_dir']}",
        f"scope: {report['scope']}",
        f"changed_paths: {summary['changed_path_count']}",
        f"python_files: {summary['python_file_count']}",
        f"symbols: {summary['symbol_count']}",
        f"issues: {summary['issue_count']}",
        f"ok: {str(summary['ok']).lower()}",
    ]
    for issue in report["issues"]:
        detail = f" :: {issue['detail']}" if issue.get("detail") else ""
        lines.append(f"- {issue['code']}: {issue['path']}{detail}")
    return "\n".join(lines) + "\n"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare changed Python AST signatures with 1:1 routing docs."
    )
    parser.add_argument("--repo", default=".", help="Git repository or child directory.")
    parser.add_argument("--routing-dir", help="Routing directory, relative to repository root.")
    parser.add_argument("--base", help="Git commit/ref used as the diff baseline.")
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Audit every tracked and untracked Python file instead of changed files.",
    )
    parser.add_argument(
        "--doc-suffix",
        default=".md",
        help="Suffix appended to the source path below routing-dir/files (default: .md).",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--output", help="Write the report to this UTF-8 path.")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        report, exit_code = audit(args)
    except AuditError as exc:
        failure = {"schema_version": 1, "error": str(exc), "summary": {"ok": False}}
        rendered = json.dumps(failure, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).resolve().write_text(rendered, encoding="utf-8")
        else:
            sys.stderr.write(rendered)
        return 2

    rendered = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else text_report(report)
    )
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
