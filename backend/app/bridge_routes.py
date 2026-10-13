"""The HTTP face of the bridge: the machine this backend runs on.

`device_routes.py` answers what the DEQ is doing. These answer whether
the machine holding the link is well, which is a different question with
a different fix. A Pi that browns out drops its USB link and its Wi-Fi,
and without this the app shows only the symptom.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.bridge_health import read_bridge_health
from app.bridge_notices import note_undervoltage, notice_log
from app.schemas import BridgeNoticeRead, BridgeRead

router = APIRouter(prefix="/bridge", tags=["bridge"])


@router.get("", response_model=BridgeRead)
def read_bridge() -> BridgeRead:
    """Returns the bridge's health, and everything that went wrong with it.

    A read raises a notice when the health says so. That lets a power dip
    outlive itself: the live reading recovers, and the notice stays until the
    bridge restarts.
    """
    health = read_bridge_health()
    note_undervoltage(notice_log, health)
    return BridgeRead(
        undervoltage_now=health.undervoltage_now,
        undervoltage_since_boot=health.undervoltage_since_boot,
        uptime_seconds=health.uptime_seconds,
        notices=[BridgeNoticeRead(**vars(notice)) for notice in notice_log.notices()],
    )
