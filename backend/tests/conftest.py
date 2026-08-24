"""Shared pytest fixtures.

`db` gives each test a MongoDB database dedicated to tests — a separate
database name from the real `Resume_Scanner`, on the same Atlas cluster —
with every collection dropped after each test. Using the real cluster
rather than a mocked client means these tests exercise the actual
unique-index/upsert behavior the app depends on for correctness (e.g. the
compound unique index that makes re-matching overwrite instead of
duplicate).
"""

import os
from collections.abc import Generator

import pytest
from pymongo import MongoClient
from pymongo.database import Database

os.environ.setdefault("GOOGLE_API_KEY", "test-placeholder-key")

from app.core.settings import settings
from app.db.mongo import ensure_indexes

TEST_DB_NAME = os.environ.get("TEST_DB_NAME", f"{settings.db_name}_test")


@pytest.fixture(scope="session")
def _test_client() -> Generator[MongoClient, None, None]:
    client: MongoClient = MongoClient(settings.mongo_url)
    yield client
    client.close()


@pytest.fixture
def db(_test_client: MongoClient) -> Generator[Database, None, None]:
    database = _test_client[TEST_DB_NAME]
    ensure_indexes(database)
    try:
        yield database
    finally:
        for name in database.list_collection_names():
            database.drop_collection(name)


@pytest.fixture
def client(db: Database):
    """A TestClient wired to the same test database the test uses, so
    assertions can inspect documents the API just wrote without a second
    connection racing the first.
    """
    from fastapi.testclient import TestClient

    from app.db.mongo import get_db
    from app.main import app

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
