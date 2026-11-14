"""The `femc` command."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from femc.convert import convert


def _convert(args: argparse.Namespace) -> int:
    dataset: Path = args.dataset
    sources: Path = args.sources or dataset.parent / "SOURCES.md"
    try:
        package = convert(dataset, sources, args.out)
    except (ValueError, OSError) as exc:
        print(f"femc: {exc}", file=sys.stderr)
        return 1
    print(package)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="femc", description="Convert datasets from FEMC's public data archive."
    )
    commands = parser.add_subparsers(dest="command")
    convert_parser = commands.add_parser(
        "convert", help="write one dataset folder as a package under the out folder"
    )
    convert_parser.add_argument("dataset", type=Path, help="a practice-data/femc/<dataset> folder")
    convert_parser.add_argument("out", type=Path, help="the folder the package is written in")
    convert_parser.add_argument(
        "--sources",
        type=Path,
        metavar="FILE",
        help="the SOURCES.md with the dataset's row (default: the one beside the dataset folder)",
    )
    convert_parser.set_defaults(run=_convert)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    code: int = args.run(args)
    return code
