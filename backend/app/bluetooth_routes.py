"""The HTTP face of the BLE bridge's pairing window. See `bluetooth_pairing.py`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.bluetooth_pairing import BluetoothPairing, PairingStatus, get_bluetooth_pairing
from app.schemas import BluetoothPairingRead, BluetoothSettingsWrite

router = APIRouter(prefix="/bluetooth", tags=["bluetooth"])


@router.get("", response_model=BluetoothPairingRead)
def read_bluetooth(pairing: BluetoothPairing = Depends(get_bluetooth_pairing)) -> BluetoothPairingRead:
    return pairing_read(pairing.read())


@router.put("/settings", response_model=BluetoothPairingRead)
def write_settings(
    body: BluetoothSettingsWrite, pairing: BluetoothPairing = Depends(get_bluetooth_pairing)
) -> BluetoothPairingRead:
    require_bridge(pairing)
    return pairing_read(pairing.set_pair_at_car_start(body.pair_at_car_start))


@router.post("/pairing-window", status_code=202)
def open_pairing_window(pairing: BluetoothPairing = Depends(get_bluetooth_pairing)) -> None:
    require_bridge(pairing)
    pairing.request_window()


def require_bridge(pairing: BluetoothPairing) -> None:
    if not pairing.read().supported:
        raise HTTPException(status_code=503, detail="this machine has no BLE bridge")


def pairing_read(status: PairingStatus) -> BluetoothPairingRead:
    return BluetoothPairingRead(**vars(status))
