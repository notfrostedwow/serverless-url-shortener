"""Run actual checks and save stdout, stderr, commands and exit codes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    (root / ".tmp").mkdir(exist_ok=True)
    commands = [
        ["-m", "pytest", "-q", "--basetemp=.tmp/pytest"],
        ["-m", "ruff", "check", "."],
        ["-m", "ruff", "format", "--check", "."],
        ["-m", "mypy", "src", "--cache-dir=.cache/mypy"],
        ["-m", "pip", "check"],
        ["tools/validate_iac.py"],
    ]
    transcript = ["Actual local checks; no remote workflow or AWS integration implied.\n"]
    failed = False
    for args in commands:
        result = subprocess.run(  # noqa: S603
            [sys.executable, *args],
            cwd=root,
            capture_output=True,
            text=True,
            env=dict(os.environ, PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1"),
            check=False,
        )
        section = (
            f"\n$ python {' '.join(args)}\n{result.stdout}{result.stderr}"
            f"exit_code={result.returncode}\n"
        )
        print(section, end="", flush=True)
        transcript.append(section)
        failed |= result.returncode != 0
    destination = root / "docs" / "validation"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "checks.txt").write_text("".join(transcript), encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
