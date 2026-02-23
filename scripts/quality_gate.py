from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Sequence

LINT_TARGETS: list[str] = [
    "app/core/services/ai",
    "app/core/services/project_service.py",
    "app/core/services/format_service.py",
    "app/modules/api/router.py",
    "tests/test_ai_service.py",
    "tests/test_api_integration.py",
    "tests/test_gemini_client.py",
    "scripts/check_encoding.py",
    "scripts/check_mojibake.py",
]

TYPECHECK_TARGETS: list[str] = [
    "app/core/services/ai",
    "app/core/services/project_service.py",
    "app/core/services/format_service.py",
]


def _run(cmd: Sequence[str]) -> None:
    printable = " ".join(cmd)
    print(f"$ {printable}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def run_lint(python_bin: str) -> None:
    _run([python_bin, "-m", "ruff", "check", *LINT_TARGETS])
    _run([python_bin, "-m", "ruff", "format", "--check", *LINT_TARGETS])


def run_typecheck(python_bin: str) -> None:
    _run(
        [
            python_bin,
            "-m",
            "mypy",
            "--config-file",
            "mypy.ini",
            *TYPECHECK_TARGETS,
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run reproducible quality gates for GicaGen."
    )
    parser.add_argument(
        "gate",
        nargs="?",
        default="all",
        choices=("lint", "typecheck", "all"),
        help="Gate to run.",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable to run commands with.",
    )
    args = parser.parse_args()

    if args.gate in ("lint", "all"):
        run_lint(args.python_bin)
    if args.gate in ("typecheck", "all"):
        run_typecheck(args.python_bin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

