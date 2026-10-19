# scripts/audit_routing.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../scripts/audit_routing.py)
- [기준·변경 전후·검증·남은 연결](../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

routing-doc-auditor 스킬의 AST/Git 검사기를 저장소 CI용으로 포함합니다. 클래스/함수 시그니처와 짝 문서·색인·삭제 소스를 검사하며 코드/문서를 수정하지 않습니다. 전체 scope와 담당 밖 누락을 분리해 보고합니다.

## AST 시그니처

```python
class AuditError(RuntimeError)
class Symbol
run_git(repo: Path, *arguments: str, binary: bool=False) -> bytes | str
nul_paths(payload: bytes) -> set[str]
repository_root(value: str) -> Path
changed_paths(repo: Path, base: str | None, include_all: bool) -> list[str]
select_routing_dir(repo: Path, value: str | None) -> Path
expression(node: ast.AST | None) -> str | None
decorator_names(nodes: list[ast.expr]) -> list[str]
function_symbol(node: ast.FunctionDef | ast.AsyncFunctionDef, owner: str | None=None) -> Symbol
extract_symbols(path: Path) -> tuple[list[Symbol], str | None]
compact(value: str) -> str
mark_documented(symbols: list[Symbol], document: str) -> list[str]
relative_display(path: Path, root: Path) -> str
audit(args: argparse.Namespace) -> tuple[dict[str, Any], int]
text_report(report: dict[str, Any]) -> str
parse_arguments() -> argparse.Namespace
main() -> int
```
