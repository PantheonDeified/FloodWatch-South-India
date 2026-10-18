#!/usr/bin/env python3
"""Syntax-check inline JavaScript in index.html using Node.js."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

HTML_PATH = Path("index.html")
SCRIPT_PATTERN = re.compile(r"<script\b[^>]*>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)


def main() -> int:
    if not HTML_PATH.is_file():
        raise SystemExit("index.html not found")
    html = HTML_PATH.read_text(encoding="utf-8")
    scripts = [match.strip() for match in SCRIPT_PATTERN.findall(html) if match.strip()]
    if not scripts:
        raise SystemExit("No inline JavaScript blocks found in index.html")

    # The page currently has one inline application script. Check each block
    # independently so a syntax error is reported against a small source file.
    for index, script in enumerate(scripts, start=1):
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(script)
            temp_path = Path(handle.name)
        try:
            result = subprocess.run(["node", "--check", str(temp_path)], check=False, text=True, capture_output=True)
            if result.returncode:
                print(result.stderr, end="")
                raise SystemExit(f"Inline JavaScript block {index} failed Node.js syntax validation")
        finally:
            temp_path.unlink(missing_ok=True)
    print(f"JavaScript syntax check passed for {len(scripts)} inline block(s) in {HTML_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
