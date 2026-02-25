"""Shared test fixtures for GicaGen tests."""
import sys
from pathlib import Path

# Ensure the project root is in sys.path so that `app.*` imports work
# when running pytest from the repo root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
