"""Moves a person's own library between two databases, as one JSON file.

The Pi's database and a copy on a laptop are two SQLite files with no sync.
An export holds what only the person made: the custom profiles, the custom
EQs, and the stars on factory presets. An import adds them. It never
changes or deletes what is there, and it skips an item that the library
holds already with the same name and content. So an import of the same
file twice adds nothing the second time.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import Equalizer, Profile
from app.schemas import LibraryEqualizer, LibraryExport, LibraryImportRead, LibraryProfile


def export_library(session: Session) -> LibraryExport:
    profiles = session.exec(select(Profile)).all()
    equalizers = session.exec(select(Equalizer)).all()
    return LibraryExport(
        profiles=[library_profile(profile) for profile in profiles if profile.source == "custom"],
        equalizers=[
            LibraryEqualizer(name=equalizer.name, favorite=equalizer.favorite, gains=list(equalizer.gains))
            for equalizer in equalizers
            if equalizer.source == "custom"
        ],
        starred_factory_profiles=sorted(
            profile.name for profile in profiles if profile.source == "factory" and profile.favorite
        ),
        starred_factory_equalizers=sorted(
            equalizer.name for equalizer in equalizers if equalizer.source == "factory" and equalizer.favorite
        ),
    )


def library_profile(profile: Profile) -> LibraryProfile:
    return LibraryProfile(
        name=profile.name,
        brand_name=profile.brand_name,
        car_model=profile.car_model,
        speaker_type=profile.speaker_type,
        supported_processors=list(profile.supported_processors),
        favorite=profile.favorite,
        data=profile.data,
    )


def import_library(session: Session, library: LibraryExport) -> LibraryImportRead:
    profiles_added, profiles_skipped = import_profiles(session, library.profiles)
    equalizers_added, equalizers_skipped = import_equalizers(session, library.equalizers)
    stars_added = star_factory_items(session, Profile, library.starred_factory_profiles)
    stars_added += star_factory_items(session, Equalizer, library.starred_factory_equalizers)
    session.commit()
    return LibraryImportRead(
        profiles_added=profiles_added,
        equalizers_added=equalizers_added,
        skipped=profiles_skipped + equalizers_skipped,
        stars_added=stars_added,
    )


def import_profiles(session: Session, profiles: list[LibraryProfile]) -> tuple[int, int]:
    existing = {
        profile_key(library_profile(profile))
        for profile in session.exec(select(Profile).where(Profile.source == "custom")).all()
    }
    added = 0
    for profile in profiles:
        key = profile_key(profile)
        if key in existing:
            continue
        existing.add(key)
        session.add(
            Profile(
                name=profile.name,
                source="custom",
                brand_name=profile.brand_name,
                car_model=profile.car_model,
                speaker_type=profile.speaker_type,
                supported_processors=list(profile.supported_processors),
                favorite=profile.favorite,
                data=profile.data.model_dump(mode="json"),
            )
        )
        added += 1
    return added, len(profiles) - added


def profile_key(profile: LibraryProfile) -> str:
    """The name and the tuning, as one comparable text. The star is not
    part of it: a star alone does not make a second profile."""
    return profile.model_copy(update={"favorite": False}).model_dump_json()


def import_equalizers(session: Session, equalizers: list[LibraryEqualizer]) -> tuple[int, int]:
    existing = {
        (equalizer.name, tuple(equalizer.gains))
        for equalizer in session.exec(select(Equalizer).where(Equalizer.source == "custom")).all()
    }
    added = 0
    for equalizer in equalizers:
        key = (equalizer.name, tuple(equalizer.gains))
        if key in existing:
            continue
        existing.add(key)
        session.add(Equalizer(name=equalizer.name, source="custom", favorite=equalizer.favorite, gains=list(equalizer.gains)))
        added += 1
    return added, len(equalizers) - added


def star_factory_items(session: Session, model: type[Profile] | type[Equalizer], names: list[str]) -> int:
    """Stars each factory item by name. A name that this install does not
    have, from another version's presets, is left out."""
    wanted = set(names)
    starred = 0
    for item in session.exec(select(model).where(model.source == "factory")).all():
        if item.name in wanted and not item.favorite:
            item.favorite = True
            session.add(item)
            starred += 1
    return starred
