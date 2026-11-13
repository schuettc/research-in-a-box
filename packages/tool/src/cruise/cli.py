import argparse
from collections.abc import Sequence

from cruise import __version__


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cruise")
    parser.add_argument("--version", action="version", version=f"cruise {__version__}")
    parser.parse_args(argv)
