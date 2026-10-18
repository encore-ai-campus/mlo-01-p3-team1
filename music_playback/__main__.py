"""Command-line entry for the local occasion-screened candidate builder."""
import argparse
import json
from pathlib import Path

from .candidates import build
from .verify import verify_general


def main():
    parser = argparse.ArgumentParser(description="음악 시즌·행사 메타데이터 사전 스크린과 일반 후보 생성")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--source", type=Path, required=True)
        command.add_argument("--analysis-dir", type=Path, default=Path("analysis/weather_music_20261016"))
        command.add_argument("--output", type=Path)
        if name == "build":
            command.add_argument("--overrides", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        result = verify_general(args.source, args.analysis_dir, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    result = build(args.source, args.analysis_dir, args.output, args.overrides)
    print(json.dumps({"source_screen_counts": result["source_screen_counts"], "coverage": result["coverage"],
                      "examples": {code: value["status"] for code, value in result["examples"].items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
