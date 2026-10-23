"""The HTTP face of the bridge: the machine this backend runs on.

`device_routes.py` answers what the DEQ is doing. These answer whether
the machine holding the link is well, which is a different question with
a different fix. A Pi that browns out drops its USB link and its Wi-Fi,
and without this the app shows only the symptom.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.bridge_health import read_bridge_health
from app.bridge_notices import note_undervoltage, notice_log
from app.bridge_system import read_bridge_system
from app.frontend_bundle import FrontendBundle, build_frontend_bundle
from app.schemas import BridgeNoticeRead, BridgeRead, BridgeSystemRead, FrontendBundleRead, FrontendPartRead, NetworkInterfaceRead

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


@router.get("/system", response_model=BridgeSystemRead)
def read_system() -> BridgeSystemRead:
    """Returns the bridge's memory, disk, network, load and build."""
    system = read_bridge_system()
    fields = vars(system) | {
        "interfaces": [NetworkInterfaceRead(**vars(interface)) for interface in system.interfaces],
    }
    return BridgeSystemRead(**fields)


@router.get("/frontend", response_model=FrontendBundleRead)
def read_frontend() -> FrontendBundleRead:
    """Describes the web app that the bridge serves, for the car app's copy.

    See `frontend_bundle.py`. A backend with no build answers 404.
    """
    bundle = require_bundle()
    return FrontendBundleRead(
        build=bundle.build,
        sha256=bundle.sha256,
        file_count=bundle.file_count,
        part_count=bundle.part_count,
    )


@router.get("/frontend/parts/{index}", response_model=FrontendPartRead)
def read_frontend_part(index: int) -> FrontendPartRead:
    """Returns one part of the base64 zip. The reply names its build, so a
    download that spans a release starts again."""
    bundle = require_bundle()
    try:
        data = bundle.part(index)
    except IndexError:
        raise HTTPException(status_code=404, detail=f"no part {index}") from None
    return FrontendPartRead(build=bundle.build, index=index, data=data)


def require_bundle() -> FrontendBundle:
    bundle = build_frontend_bundle()
    if bundle is None:
        raise HTTPException(status_code=404, detail="this bridge serves no built web app")
    return bundle
