"""Command-line argument helpers shared by the FIRETRACE CLIs."""

from __future__ import annotations

import re

_NUMBER_LIST = re.compile(r"^-\d+(\.\d+)?(,-?\d+(\.\d+)?)*$")


def attach_negative_values(argv: list[str], options: tuple[str, ...] = ("--bbox",)) -> list[str]:
    """Rewrite ``--bbox -150,-30,-140,-20`` as ``--bbox=-150,-30,-140,-20``.

    argparse treats a value starting with '-' as a new option, which breaks every
    bbox west of Greenwich or south of the equator. Only values that are
    comma-separated numbers are joined, so real options are never swallowed.
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in options and i + 1 < len(argv) and _NUMBER_LIST.match(argv[i + 1]):
            out.append(f"{token}={argv[i + 1]}")
            i += 2
            continue
        out.append(token)
        i += 1
    return out
