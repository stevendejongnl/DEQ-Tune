"""The HTTP face of the Pi's release updater. See `updates.py`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.schemas import UpdateHistoryRead, UpdatesRead, UpdateSettingsWrite
from app.updates import ReleaseUpdates, UpdateStatus, get_release_updates

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("", response_model=UpdatesRead)
def read_updates(updates: ReleaseUpdates = Depends(get_release_updates)) -> UpdatesRead:
    return updates_read(updates.read())


@router.put("/settings", response_model=UpdatesRead)
def write_settings(
    body: UpdateSettingsWrite, updates: ReleaseUpdates = Depends(get_release_updates)
) -> UpdatesRead:
    require_updater(updates)
    return updates_read(updates.set_automatic(body.automatic))


@router.post("/request", status_code=202)
def request_update(updates: ReleaseUpdates = Depends(get_release_updates)) -> None:
    require_updater(updates)
    updates.request_update()


def require_updater(updates: ReleaseUpdates) -> None:
    if not updates.read().supported:
        raise HTTPException(status_code=503, detail="this machine has no release updater")


def updates_read(status: UpdateStatus) -> UpdatesRead:
    fields = vars(status) | {"history": [UpdateHistoryRead(**vars(entry)) for entry in status.history]}
    return UpdatesRead(**fields)
