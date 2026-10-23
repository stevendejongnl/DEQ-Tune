"""Checks the web app bundle that the car app fetches."""

from __future__ import annotations

import base64
import io
import zipfile

from app.frontend_bundle import build_frontend_bundle, read_frontend_build


def make_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    (dist / "assets" / "index-abc.js").write_text("console.log(1)")
    (dist / "build-id.txt").write_text("8e77c24-2026-10-23T17:26\n")
    return dist


def test_the_bundle_carries_every_file_and_the_build(tmp_path):
    bundle = build_frontend_bundle(make_dist(tmp_path))

    assert bundle.build == "8e77c24-2026-10-23T17:26"
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(bundle.archive_base64)))
    assert sorted(archive.namelist()) == ["assets/index-abc.js", "build-id.txt", "index.html"]
    assert bundle.file_count == 3


def test_no_build_means_no_bundle(tmp_path):
    assert build_frontend_bundle(tmp_path / "missing") is None
    assert read_frontend_build(tmp_path / "missing") is None
