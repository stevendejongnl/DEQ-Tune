"""Checks the web app bundle that the car app fetches."""

from __future__ import annotations

import base64
import hashlib
import io
import random
import zipfile

from app import frontend_bundle
from app.frontend_bundle import PART_CHARACTERS, build_frontend_bundle, read_frontend_build


def make_dist(tmp_path, build="8e77c24-2026-10-23T17:26", script_size=10):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("<html></html>")
    # Random bytes do not compress, so a test can force many parts.
    (dist / "assets" / "index-abc.js").write_bytes(random.Random(1).randbytes(script_size * 64))
    (dist / "build-id.txt").write_text(f"{build}\n")
    return dist


def test_the_parts_join_into_the_zip_that_the_hash_names(tmp_path):
    frontend_bundle._bundles.clear()
    bundle = build_frontend_bundle(make_dist(tmp_path, script_size=600))

    joined = "".join(bundle.part(index) for index in range(bundle.part_count))
    data = base64.b64decode(joined)

    assert bundle.part_count > 1
    assert all(len(bundle.part(index)) <= PART_CHARACTERS for index in range(bundle.part_count))
    assert hashlib.sha256(data).hexdigest() == bundle.sha256
    assert sorted(zipfile.ZipFile(io.BytesIO(data)).namelist()) == ["assets/index-abc.js", "build-id.txt", "index.html"]


def test_one_build_keeps_one_zip(tmp_path):
    frontend_bundle._bundles.clear()
    dist = make_dist(tmp_path)

    assert build_frontend_bundle(dist) is build_frontend_bundle(dist)


def test_no_build_means_no_bundle(tmp_path):
    assert build_frontend_bundle(tmp_path / "missing") is None
    assert read_frontend_build(tmp_path / "missing") is None
