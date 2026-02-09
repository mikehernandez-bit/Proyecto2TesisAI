from __future__ import annotations

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

MARKERS = (
    "\u00c3",  # U+00C3
    "\u00e2",  # U+00E2
    "\u00f0",  # U+00F0
    "\u00c2",  # U+00C2
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


def _score(text: str) -> int:
    return sum(text.count(marker) for marker in MARKERS)


def _try_fix_line(line: str) -> str:
    best = line
    best_score = _score(line)
    for enc in ("cp1252", "latin-1"):
        try:
            candidate = line.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        candidate_score = _score(candidate)
        if candidate_score < best_score:
            best = candidate
            best_score = candidate_score
    return best


def main() -> int:
    root = Path.cwd()
    changed_files = 0

    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        lines = text.splitlines(keepends=True)
        out = []
        touched = False
        for line in lines:
            if any(marker in line for marker in MARKERS):
                fixed = _try_fix_line(line)
                if fixed != line:
                    touched = True
                    out.append(fixed)
                else:
                    out.append(line)
            else:
                out.append(line)

        if touched:
            path.write_text("".join(out), encoding="utf-8")
            changed_files += 1
            print(f"Fixed: {path}")

    if changed_files == 0:
        print("No files required fixes.")
    else:
        print(f"Files fixed: {changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
