"""Where the backend finds the files that it serves but does not own."""

from __future__ import annotations

from pathlib import Path

# The built frontend. The deploy copies it to the repository root, not to
# `frontend/dist`.
DIST_DIR = Path(__file__).resolve().parents[2] / "dist"

# The frontend build writes its build id into this file. The bridge reports
# it, so the app can tell a cached page from the one the bridge serves now.
BUILD_ID_FILE_NAME = "build-id.txt"
