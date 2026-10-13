"""Allow diagnostics to run from the repository root with any activated demo venv."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web/backend"))


def preview(text, limit=240):
    return " ".join(text.split())[:limit]
