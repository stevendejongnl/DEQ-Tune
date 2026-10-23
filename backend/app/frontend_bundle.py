"""The built web app, for the phone app that carries its own copy.

The car app shows the web app from a copy inside the APK, because in the car
the phone reaches the Pi over Bluetooth only. That copy grows old with each
release that the Pi installs. So the car app compares its copy's build id
with the Pi's, and on a difference it fetches the Pi's web app once.

The web app goes as one zip, because Android unpacks a zip with no extra
library, in base64, because the Bluetooth bridge carries text. The zip is
about 150 KB in base64. One reply that size is some 850 Bluetooth
notifications in one burst, with no acknowledgement, and one lost chunk
spoils all of it. So the phone fetches it in parts of `PART_CHARACTERS`,
one request each, and checks the SHA-256 of the whole zip at the end.
"""

from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.paths import BUILD_ID_FILE_NAME, DIST_DIR

# About 90 Bluetooth notifications per part, a reply size the bridge
# carries every day.
PART_CHARACTERS = 16_000


@dataclass(frozen=True)
class FrontendBundle:
    build: str
    archive_base64: str
    sha256: str
    file_count: int

    @property
    def part_count(self) -> int:
        return max(1, -(-len(self.archive_base64) // PART_CHARACTERS))

    def part(self, index: int) -> str:
        if not 0 <= index < self.part_count:
            raise IndexError(f"part {index} of {self.part_count}")
        start = index * PART_CHARACTERS
        return self.archive_base64[start:start + PART_CHARACTERS]


def read_frontend_build(dist_dir: Path = DIST_DIR) -> str | None:
    """Returns the build id of the web app that this backend serves, or None."""
    try:
        return (dist_dir / BUILD_ID_FILE_NAME).read_text().strip() or None
    except OSError:
        return None


# One zip per build, so every part of one download comes from the same zip.
_bundles: dict[str, FrontendBundle] = {}


def build_frontend_bundle(dist_dir: Path = DIST_DIR) -> FrontendBundle | None:
    """Returns the whole web app as one zip, or None when there is no build."""
    build = read_frontend_build(dist_dir)
    if build is None:
        return None
    cached = _bundles.get(build)
    if cached is not None:
        return cached
    buffer = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(dist_dir).as_posix())
                file_count += 1
    data = buffer.getvalue()
    bundle = FrontendBundle(
        build=build,
        archive_base64=base64.b64encode(data).decode(),
        sha256=hashlib.sha256(data).hexdigest(),
        file_count=file_count,
    )
    _bundles.clear()
    _bundles[build] = bundle
    return bundle
