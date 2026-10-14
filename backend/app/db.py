from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, create_engine

DB_PATH = os.environ.get("DEQ_DB_PATH", "deq.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


# Columns added after a database already existed. `create_all` makes a
# missing table but never changes one that exists. So the Pi's database
# needs each later column added by hand, once.
ADDED_PROFILE_COLUMNS = {
    "favorite": "BOOLEAN NOT NULL DEFAULT 0",
}


def create_db_and_tables(target: Engine = engine) -> None:
    SQLModel.metadata.create_all(target)
    add_missing_profile_columns(target)


def add_missing_profile_columns(target: Engine) -> None:
    """Adds each column in `ADDED_PROFILE_COLUMNS` that the table lacks."""
    present = {column["name"] for column in inspect(target).get_columns("profile")}
    with target.begin() as connection:
        for name, definition in ADDED_PROFILE_COLUMNS.items():
            if name not in present:
                connection.execute(text(f"ALTER TABLE profile ADD COLUMN {name} {definition}"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
