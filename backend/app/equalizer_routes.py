"""The HTTP face of the EQ library.

A factory EQ comes with the app and stays read-only. A person copies one to
make their own, and edits the copy.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.active_profile import read_active_equalizer_id, write_active_equalizer_id
from app.db import get_session
from app.models import Equalizer
from app.schemas import EqualizerCreate, EqualizerRead, EqualizerUpdate, FavoriteWrite

router = APIRouter(prefix="/equalizers", tags=["equalizers"])


@router.get("", response_model=list[EqualizerRead])
def list_equalizers(session: Session = Depends(get_session)) -> list[Equalizer]:
    return session.exec(select(Equalizer)).all()


@router.post("", response_model=EqualizerRead, status_code=201)
def create_equalizer(body: EqualizerCreate, session: Session = Depends(get_session)) -> Equalizer:
    equalizer = Equalizer(name=body.name, source="custom", gains=list(body.gains))
    session.add(equalizer)
    session.commit()
    session.refresh(equalizer)
    return equalizer


@router.post("/{equalizer_id}/duplicate", response_model=EqualizerRead, status_code=201)
def duplicate_equalizer(equalizer_id: int, session: Session = Depends(get_session)) -> Equalizer:
    """Copies any EQ, a factory one too, as a custom EQ to edit."""
    source = require_equalizer(session, equalizer_id)
    copy = Equalizer(name=f"{source.name} (copy)", source="custom", gains=list(source.gains))
    session.add(copy)
    session.commit()
    session.refresh(copy)
    return copy


@router.put("/{equalizer_id}", response_model=EqualizerRead)
def update_equalizer(
    equalizer_id: int, body: EqualizerUpdate, session: Session = Depends(get_session)
) -> Equalizer:
    equalizer = require_custom_equalizer(session, equalizer_id)
    if body.name is not None:
        equalizer.name = body.name
    if body.gains is not None:
        equalizer.gains = list(body.gains)
    session.add(equalizer)
    session.commit()
    session.refresh(equalizer)
    return equalizer


@router.put("/{equalizer_id}/favorite", response_model=EqualizerRead)
def set_favorite(
    equalizer_id: int, body: FavoriteWrite, session: Session = Depends(get_session)
) -> Equalizer:
    """Stars or unstars one EQ. A factory EQ takes a star too: the star is
    the person's choice, and it leaves the curve alone."""
    equalizer = require_equalizer(session, equalizer_id)
    equalizer.favorite = body.favorite
    session.add(equalizer)
    session.commit()
    session.refresh(equalizer)
    return equalizer


@router.delete("/{equalizer_id}", status_code=204)
def delete_equalizer(equalizer_id: int, session: Session = Depends(get_session)) -> None:
    equalizer = require_custom_equalizer(session, equalizer_id)
    session.delete(equalizer)
    session.commit()
    # A deleted EQ cannot stay the one the unit plays.
    if read_active_equalizer_id(session) == equalizer_id:
        write_active_equalizer_id(session, None)


def require_equalizer(session: Session, equalizer_id: int) -> Equalizer:
    equalizer = session.get(Equalizer, equalizer_id)
    if equalizer is None:
        raise HTTPException(status_code=404, detail="EQ not found")
    return equalizer


def require_custom_equalizer(session: Session, equalizer_id: int) -> Equalizer:
    equalizer = require_equalizer(session, equalizer_id)
    if equalizer.source == "factory":
        raise HTTPException(status_code=409, detail="Factory EQs are read-only; duplicate it first")
    return equalizer
