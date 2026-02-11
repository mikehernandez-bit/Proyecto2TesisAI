from __future__ import annotations

import sys
from pathlib import Path


TEXT_EXTS = {".md", ".py", ".js", ".html", ".json", ".css", ".yml", ".yaml", ".txt"}
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".cca",
    "dist",
    "build",
}

# Prohibited markers represented with code points to avoid embedding bad glyphs.
FORBIDDEN_TOKENS = (
    "\u00c3",        # U+00C3
    "\u00e2",        # U+00E2
    "\u00f0\u0178",  # U+00F0 + U+0178
    "\u251c",        # U+251C
    "\u2502",        # U+2502
    "\u2514",        # U+2514
    "\u2500",        # U+2500
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


def _line_has_forbidden(line: str) -> bool:
    return any(token in line for token in FORBIDDEN_TOKENS)


def _preview(line: str) -> str:
    return line.strip().encode("unicode_escape", errors="ignore").decode("ascii", errors="ignore")


def main() -> int:
    root = Path.cwd()
    issues: list[tuple[Path, int, str]] = []

    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Skip non-UTF8 files; this guard checks visible mojibake patterns in UTF-8 text files.
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            if _line_has_forbidden(line):
                issues.append((path, line_no, _preview(line)))

    if issues:
        print("Encoding check failed.")
        for path, line_no, detail in issues:
            print(f"{path}:{line_no}: {detail}")
        return 1

    print("Encoding check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
