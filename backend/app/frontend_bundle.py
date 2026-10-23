"""The built web app, for the phone app that carries its own copy.

The car app shows the web app from a copy inside the APK, because in the car
the phone reaches the Pi over Bluetooth only. That copy grows old with each
release that the Pi installs. So the car app compares its copy's build id
with the Pi's, and on a difference it fetches the Pi's web app once, as one
zip in one reply. Zip, because Android unpacks it with no extra library, and
base64, because the Bluetooth bridge carries text.
"""

from __future__ import annotations

import base64
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.paths import BUILD_ID_FILE_NAME, DIST_DIR


@dataclass(frozen=True)
class FrontendBundle:
    build: str
    archive_base64: str
    file_count: int


def read_frontend_build(dist_dir: Path = DIST_DIR) -> str | None:
    """Returns the build id of the web app that this backend serves, or None."""
    try:
        return (dist_dir / BUILD_ID_FILE_NAME).read_text().strip() or None
    except OSError:
        return None


def build_frontend_bundle(dist_dir: Path = DIST_DIR) -> FrontendBundle | None:
    """Returns the whole web app as one zip, or None when there is no build."""
    build = read_frontend_build(dist_dir)
    if build is None:
        return None
    buffer = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(dist_dir).as_posix())
                file_count += 1
    return FrontendBundle(
        build=build,
        archive_base64=base64.b64encode(buffer.getvalue()).decode(),
        file_count=file_count,
    )
