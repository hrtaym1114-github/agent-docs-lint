from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .scanner import Finding, scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-docs-lint", description="Lint agent documentation for drift.")
    parser.add_argument("path", nargs="?", default=".", help="Repository or fixture path to scan.")
    parser.add_argument("--config", help="Path to agent-docs-lint TOML config.")
    parser.add_argument("--json", action="store_true", help="Print findings as JSON.")
    parser.add_argument("--warn-only", action="store_true", help="Print findings but exit 0.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        findings = scan(args.path, args.config)
    except (OSError, ValueError) as exc:
        print(f"agent-docs-lint: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([finding.to_dict() for finding in findings], indent=2, sort_keys=True))
    else:
        _print_human(findings)

    if args.warn_only:
        return 0
    return 1 if any(finding.severity == "error" for finding in findings) else 0


def _print_human(findings: list[Finding]) -> None:
    if not findings:
        print("No findings.")
        return
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.rule}: {finding.message}")


if __name__ == "__main__":
    raise SystemExit(main())
