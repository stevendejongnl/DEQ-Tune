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
    supported_processors: list[str] = Field(sa_column=Column(JSON), default_factory=list)
    data: dict = Field(sa_column=Column(JSON))
    """The `TuningData` blob (see eq_data.py), stored as-is."""
