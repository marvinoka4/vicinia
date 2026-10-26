"""Fail if any tracked file contains an em dash (U+2014)."""

import subprocess
import sys
from pathlib import Path

EM_DASH = "—"


def main() -> int:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    bad = []
    for f in files:
        p = Path(f)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if EM_DASH in line:
                bad.append(f"{f}:{n}")
    for b in bad:
        print(f"em dash found: {b}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
