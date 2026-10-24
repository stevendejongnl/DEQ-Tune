"""The HTTP face of the library export and import. See library_transfer."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.library_transfer import export_library, import_library
from app.schemas import LibraryExport, LibraryImportRead

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/export", response_model=LibraryExport)
def read_library_export(session: Session = Depends(get_session)) -> LibraryExport:
    return export_library(session)


@router.post("/import", response_model=LibraryImportRead)
def import_library_file(library: LibraryExport, session: Session = Depends(get_session)) -> LibraryImportRead:
    return import_library(session, library)
