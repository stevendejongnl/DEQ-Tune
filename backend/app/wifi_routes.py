"""The HTTP face of the bridge's Wi-Fi networks and its access point.

A save or a forget changes the saved networks only. The bridge joins a saved
network on its own, or after `POST /wifi/join`. A new access point key
applies at the access point's next start.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException

from app.schemas import (
    AccessPointKeyWrite,
    AccessPointRead,
    SavedWifiNetworkRead,
    VisibleWifiNetworkRead,
    WifiForgetWrite,
    WifiNetworkWrite,
    WifiRead,
)
from app.wifi_networks import (
    AccessPoint,
    SavedNetwork,
    WifiNetworks,
    WifiRefused,
    WifiUnavailable,
    get_wifi_networks,
)

router = APIRouter(prefix="/wifi", tags=["wifi"])


@router.get("", response_model=WifiRead)
def read_wifi(networks: WifiNetworks = Depends(get_wifi_networks)) -> WifiRead:
    with helper_errors_as_http():
        return wifi_read(networks.saved(), networks)


@router.post("/networks", response_model=WifiRead)
def save_network(body: WifiNetworkWrite, networks: WifiNetworks = Depends(get_wifi_networks)) -> WifiRead:
    with helper_errors_as_http():
        return wifi_read(networks.save(body.ssid, body.password), networks)


@router.post("/forget", response_model=WifiRead)
def forget_network(body: WifiForgetWrite, networks: WifiNetworks = Depends(get_wifi_networks)) -> WifiRead:
    with helper_errors_as_http():
        return wifi_read(networks.forget(body.ssid), networks)


@router.post("/join", status_code=202)
def join_network(networks: WifiNetworks = Depends(get_wifi_networks)) -> None:
    with helper_errors_as_http():
        networks.request_join()


@router.get("/access-point", response_model=AccessPointRead)
def read_access_point(networks: WifiNetworks = Depends(get_wifi_networks)) -> AccessPointRead:
    with helper_errors_as_http():
        return access_point_read(networks.access_point())


@router.put("/access-point/key", response_model=AccessPointRead)
def set_access_point_key(
    body: AccessPointKeyWrite, networks: WifiNetworks = Depends(get_wifi_networks)
) -> AccessPointRead:
    with helper_errors_as_http():
        return access_point_read(networks.set_access_point_key(body.key))


def access_point_read(access_point: AccessPoint | None) -> AccessPointRead:
    if access_point is None:
        raise HTTPException(status_code=404, detail="The Pi has no access point.")
    return AccessPointRead(**vars(access_point))


def wifi_read(saved: list[SavedNetwork], networks: WifiNetworks) -> WifiRead:
    return WifiRead(
        saved=[SavedWifiNetworkRead(**vars(network)) for network in saved],
        visible=[VisibleWifiNetworkRead(**vars(network)) for network in networks.visible()],
    )


@contextmanager
def helper_errors_as_http() -> Iterator[None]:
    """Turns the helper's two failures into the two HTTP answers.

    503 means this machine cannot manage Wi-Fi at all. 409 means the helper
    refused this one request, most often because the DEQ holds the link.
    """
    try:
        yield
    except WifiUnavailable as caught_error:
        raise HTTPException(status_code=503, detail=str(caught_error)) from caught_error
    except WifiRefused as caught_error:
        raise HTTPException(status_code=409, detail=str(caught_error)) from caught_error
