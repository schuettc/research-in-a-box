import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from archive_contract.config import load_config
from archive_contract.findings import Finding
from archive_contract.profile import Profile, load_profile
from cruise import __version__
from cruise.diagnose import Diagnosis, diagnose
from cruise.rules import REGISTRY

HEADINGS = {
    "structure": "Structure",
    "find": "Can I find, cite and reuse it?",
    "understand": "Can I understand each column?",
    "trust": "Can I trust the values?",
}


class SelectionError(Exception):
    """A profile or archive config that can't be loaded."""


def _selection(args: argparse.Namespace) -> tuple[list[Profile], list[str]]:
    """The profiles and extra required fields from --config and --profile."""
    try:
        return _load_selection(args)
    except (ValueError, OSError) as exc:
        raise SelectionError(str(exc)) from exc


def _load_selection(args: argparse.Namespace) -> tuple[list[Profile], list[str]]:
    profiles: list[Profile] = []
    required: list[str] = []
    if args.config is not None:
        config = load_config(args.config)
        profiles.extend(config.load_profiles())
        required.extend(config.required)
    profiles.extend(load_profile(name) for name in args.profile)
    return profiles, required


def _group(finding: Finding) -> str:
    try:
        return REGISTRY.get(finding.rule_id).question
    except KeyError:
        return "structure"


def _target(finding: Finding) -> str:
    target = finding.target
    if target is None:
        return "package"
    if target.resource and target.field:
        return f"{target.resource}.{target.field}"
    return target.resource or target.path or target.field or "package"


def _evidence(finding: Finding) -> str | None:
    evidence = finding.evidence
    if evidence is None:
        return None
    parts: list[str] = []
    if evidence.rows:
        rows = ", ".join(str(r) for r in evidence.rows)
        parts.append(f"rows {rows}")
    if evidence.values:
        parts.append("values " + ", ".join(json.dumps(v) for v in evidence.values))
    if evidence.count is not None:
        parts.append(f"{evidence.count} row{'' if evidence.count == 1 else 's'} in all")
    return "; ".join(parts) or None


def verdict(errors: int, warnings: int, notes: int) -> str:
    if errors:
        return f"blocks publishing ({errors})"
    line = f"publishable, with {warnings} warning{'' if warnings == 1 else 's'}"
    if notes:
        line += f" and {notes} note{'' if notes == 1 else 's'}"
    return line


def counts(findings: list[Finding]) -> tuple[int, int, int]:
    """Errors, warnings and notes."""
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    return errors, warnings, len(findings) - errors - warnings


def _print_text(result: Diagnosis) -> None:
    print(result.path)
    for group, heading in HEADINGS.items():
        findings = [f for f in result.findings if _group(f) == group]
        if not findings:
            continue
        print(f"\n{heading}")
        for finding in findings:
            print(f"  {finding.severity}  {finding.rule_id}  {_target(finding)}")
            print(f"    {finding.message}")
            evidence = _evidence(finding)
            if evidence:
                print(f"    evidence: {evidence}")
            if finding.suggested_fix:
                print(f"    fix: {finding.suggested_fix}")
    print()
    print(f"Score: {result.score.line() if result.score else 'not scored'}")
    print(f"Verdict: {verdict(*counts(result.findings))}")


def _diagnose(args: argparse.Namespace) -> int:
    profiles, required = _selection(args)
    try:
        result = diagnose(args.folder, profiles, required)
    except ValueError as exc:  # a profile switching on a rule that doesn't exist
        raise SelectionError(str(exc)) from exc
    if args.json:
        data = {
            "validation": result.validation.dump(),
            "quality": result.quality.dump() if result.quality else None,
            "findings": [f.dump() for f in result.findings],
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        _print_text(result)
    return 1 if result.blocking else 0


def _selection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument(
        "--profile", action="append", default=[], metavar="NAME", help="apply a profile"
    )
    parser.add_argument("--config", type=Path, metavar="FILE", help="the archive config")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cruise")
    parser.add_argument("--version", action="version", version=f"cruise {__version__}")
    commands = parser.add_subparsers(dest="command")
    diagnose_parser = commands.add_parser("diagnose", help="check one package folder")
    diagnose_parser.add_argument("folder", type=Path)
    _selection_options(diagnose_parser)
    diagnose_parser.set_defaults(run=_diagnose)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        code: int = args.run(args)
    except SelectionError as exc:
        print(f"cruise: {exc}", file=sys.stderr)
        return 2
    return code
