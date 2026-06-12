"""Rewrite agent-lc module names to their plugin equivalents in ported code.

Usage: python scripts/port_rewrite.py <directory> [<directory> ...]
"""
import pathlib
import sys

REWRITES = [
    ("livingcolor_constants", "lc_constants"),
    ("livingcolor_server", "lc_server"),
]

for target in sys.argv[1:]:
    for path in pathlib.Path(target).rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        new = text
        for old, repl in REWRITES:
            new = new.replace(old, repl)
        if new != text:
            path.write_text(new, encoding="utf-8")
            print(f"rewrote {path}")
