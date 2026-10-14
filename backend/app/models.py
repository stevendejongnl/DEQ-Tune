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
    """What the unit should play: the car profile, the EQ on top of it, and
    the source mode. The table holds one row at most.

    It lives in the database, so the choice outlives a restart of the backend.
    The unit gets all three each time its link comes up."""

    id: int = Field(default=1, primary_key=True)
    profile_id: int | None = None
    equalizer_id: int | None = None
    # A name from the AUDIO_SOURCE enum. None means the default.
    source_mode: str | None = None


class Equalizer(SQLModel, table=True):
    """A music-style EQ curve. The unit plays it on top of the car profile's
    own curve.

    A factory EQ comes with the app and stays read-only. A custom EQ is the
    person's own, often a copy of a factory one."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    source: str = Field(default="custom")  # "factory" | "custom"
    # A starred EQ shows in the EQ panel and the car app. The rest stay in
    # the library. An EQ of the person's own shows either way.
    favorite: bool = Field(default=False)
    gains: list[float] = Field(sa_column=Column(JSON))
    """13 gains in dB, 50 Hz to 12.5 kHz."""
