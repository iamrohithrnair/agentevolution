"""Pytest fixtures for the Dronan test suite.

Provides a fresh in-memory mongomock-motor database per test so the unit
tier stays hermetic. Integration tests that require a real Atlas cluster
should be marked ``integration`` and gated behind the ``DRONAN_REAL_ATLAS=1``
environment variable.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio


def real_atlas_required() -> bool:
    """True only when ``DRONAN_REAL_ATLAS=1`` is set and a URI is reachable."""
    return os.environ.get("DRONAN_REAL_ATLAS") == "1" and bool(
        os.environ.get("MONGODB_URI")
        or os.environ.get("MONGODB_ATLAS_URI")
        or os.environ.get("ATLAS_CONNECTION_STRING")
    )


@pytest_asyncio.fixture
async def mongo_client() -> AsyncGenerator:
    """Yield a mongomock-motor client (closes on teardown)."""
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    try:
        yield client
    finally:
        client.close()


@pytest_asyncio.fixture
async def mongo_db(mongo_client) -> AsyncGenerator:
    """Yield a fresh database per test (unique name to guarantee isolation)."""
    name = f"dronan_test_{uuid.uuid4().hex[:8]}"
    yield mongo_client[name]
    await mongo_client.drop_database(name)


def pytest_configure(config: pytest.Config) -> None:
    """Register custom marks so pytest doesn't warn on `pytest.mark.unit`."""
    config.addinivalue_line("markers", "unit: fast hermetic test (default).")
    config.addinivalue_line(
        "markers",
        "integration: requires DRONAN_REAL_ATLAS=1 and a reachable MongoDB.",
    )
