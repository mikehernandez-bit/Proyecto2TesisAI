from __future__ import annotations

import sys
from pathlib import Path


TEXT_EXTS = {".py", ".js", ".html", ".md", ".json", ".css"}
EXCLUDE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cca", "dist", "build"}

# Forbidden tokens encoded via unicode escapes.
FORBIDDEN_TOKENS = (
    "\u00c3",
    "\u00e2",
    "\u00f0\u0178",
    "\u251c",
    "\u2502",
    "\u2514",
    "\u2500",
)


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if _is_excluded(path):
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        yield path


def _preview(line: str) -> str:
    return line.rstrip().encode("unicode_escape", errors="ignore").decode("ascii", errors="ignore")


def main() -> int:
    root = Path.cwd()
    issues: list[tuple[Path, int, str]] = []

    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Skip non UTF-8 files; this check targets visible mojibake patterns in source text files.
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(token in line for token in FORBIDDEN_TOKENS):
                issues.append((path, line_no, _preview(line)))

    if issues:
        print("Mojibake check failed.")
        for file_path, line_no, preview in issues:
            print(f"{file_path}:{line_no}: {preview}")
        return 1

    print("Mojibake check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
