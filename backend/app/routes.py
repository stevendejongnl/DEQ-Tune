from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.active_profile import read_active_profile_id, write_active_profile_id
from app.models import Profile
from app.schemas import FavoriteWrite, ProfileCreate, ProfileRead, ProfileUpdate

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileRead])
def list_profiles(session: Session = Depends(get_session)) -> list[Profile]:
    return session.exec(select(Profile)).all()


@router.get("/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: int, session: Session = Depends(get_session)) -> Profile:
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.post("", response_model=ProfileRead, status_code=201)
def create_profile(body: ProfileCreate, session: Session = Depends(get_session)) -> Profile:
    profile = Profile(
        name=body.name,
        source="custom",
        brand_name=body.brand_name,
        car_model=body.car_model,
        speaker_type=body.speaker_type,
        supported_processors=body.supported_processors,
        data=body.data.model_dump(mode="json"),
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.put("/{profile_id}", response_model=ProfileRead)
def update_profile(
    profile_id: int, body: ProfileUpdate, session: Session = Depends(get_session)
) -> Profile:
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.source == "factory":
        raise HTTPException(
            status_code=409, detail="Factory profiles are read-only; duplicate it first"
        )

    if body.name is not None:
        profile.name = body.name
    if body.data is not None:
        profile.data = body.data.model_dump(mode="json")

    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.put("/{profile_id}/favorite", response_model=ProfileRead)
def set_favorite(
    profile_id: int, body: FavoriteWrite, session: Session = Depends(get_session)
) -> Profile:
    """Stars or unstars one profile. A factory preset takes a star too: the
    star is the person's choice, and it leaves the preset's tuning alone."""
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.favorite = body.favorite
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, session: Session = Depends(get_session)) -> None:
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.source == "factory":
        raise HTTPException(status_code=409, detail="Factory profiles cannot be deleted")

    session.delete(profile)
    session.commit()
    # A deleted profile cannot stay the one the unit should play.
    if read_active_profile_id(session) == profile_id:
        write_active_profile_id(session, None)


@router.post("/{profile_id}/duplicate", response_model=ProfileRead, status_code=201)
def duplicate_profile(profile_id: int, session: Session = Depends(get_session)) -> Profile:
    source = session.get(Profile, profile_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    copy = Profile(
        name=f"{source.name} (copy)",
        source="custom",
        brand_name=source.brand_name,
        car_model=source.car_model,
        speaker_type=source.speaker_type,
        supported_processors=source.supported_processors,
        data=source.data,
    )
    session.add(copy)
    session.commit()
    session.refresh(copy)
    return copy
