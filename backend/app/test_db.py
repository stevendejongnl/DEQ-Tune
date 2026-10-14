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


def test_an_older_setting_table_gets_the_eq_and_source_columns():
    """The Pi's database got activeprofilesetting with one column on
    2026-10-14. The EQ and the source mode came a day later."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE activeprofilesetting (id INTEGER PRIMARY KEY, profile_id INTEGER)"
        ))
        connection.execute(text("INSERT INTO activeprofilesetting VALUES (1, 15)"))

    create_db_and_tables(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("activeprofilesetting")}
    assert {"equalizer_id", "source_mode"} <= columns
    with engine.connect() as connection:
        assert connection.execute(text("SELECT profile_id FROM activeprofilesetting")).scalar_one() == 15


def test_an_older_equalizer_table_gets_the_favorite_column():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE equalizer (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL,"
            " source VARCHAR NOT NULL, gains JSON)"
        ))

    added = create_db_and_tables(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("equalizer")}
    assert "favorite" in columns
    assert ("equalizer", "favorite") in added
