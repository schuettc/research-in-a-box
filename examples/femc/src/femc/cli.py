"""The `femc` command."""

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="femc", description="Convert datasets from FEMC's public data archive."
    )
    parser.add_subparsers(dest="command")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
    return 0
