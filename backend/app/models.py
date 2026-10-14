from __future__ import annotations

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Profile(SQLModel, table=True):
    """A DEQ tuning profile. The seed loads factory profiles read-only from the
    bundled Pioneer presets. An edit of one duplicates it as `custom`."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    source: str = Field(default="custom")  # "factory" | "custom"
    brand_name: str | None = None
    car_model: str | None = None
    speaker_type: str | None = None  # "general" | "carrozzeria" | None
    # A starred preset shows in the sidebar. The rest stay in the library.
    favorite: bool = Field(default=False)
    supported_processors: list[str] = Field(sa_column=Column(JSON), default_factory=list)
    data: dict = Field(sa_column=Column(JSON))
    """The `TuningData` blob (see eq_data.py), stored as-is."""


class ActiveProfileSetting(SQLModel, table=True):
    """Which profile the unit should play. The table holds one row at most.

    It lives in the database, so the choice outlives a restart of the backend.
    The unit gets the profile each time its link comes up."""

    id: int = Field(default=1, primary_key=True)
    profile_id: int | None = None
