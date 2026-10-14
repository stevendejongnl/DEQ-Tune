"""Checks that an existing database gets the columns added after it."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlmodel import create_engine
from sqlmodel.pool import StaticPool

from app.db import create_db_and_tables


def test_an_older_profile_table_gets_the_favorite_column():
    """The Pi's database predates `favorite`. `create_all` leaves an existing
    table as it is, so startup has to add the column itself."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE profile (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL,"
            " source VARCHAR NOT NULL, brand_name VARCHAR, car_model VARCHAR,"
            " speaker_type VARCHAR, supported_processors JSON, data JSON)"
        ))
        connection.execute(text(
            "INSERT INTO profile (name, source, data) VALUES ('old', 'custom', '{}')"
        ))

    create_db_and_tables(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("profile")}
    assert "favorite" in columns
    with engine.connect() as connection:
        assert connection.execute(text("SELECT favorite FROM profile")).scalar_one() == 0


def test_a_second_start_changes_nothing():
    engine = create_engine("sqlite://", poolclass=StaticPool)

    create_db_and_tables(engine)
    create_db_and_tables(engine)

    columns = [column["name"] for column in inspect(engine).get_columns("profile")]
    assert columns.count("favorite") == 1
