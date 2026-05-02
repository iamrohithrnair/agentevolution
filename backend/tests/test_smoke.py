"""Phase 0 smoke test — asserts we can import the package and (optionally) ping Atlas."""

from __future__ import annotations

import asyncio
import os

import pytest


def test_package_importable() -> None:
    import dronan

    assert dronan.__version__


def test_config_loads() -> None:
    from dronan.config import get_settings

    s = get_settings()
    assert s.mongodb_db


@pytest.mark.skipif(
    not (
        os.environ.get("MONGODB_URI")
        or os.environ.get("MONGODB_ATLAS_URI")
        or os.environ.get("ATLAS_CONNECTION_STRING")
    ),
    reason="No MONGODB_URI configured; skipping live ping.",
)
def test_atlas_ping() -> None:
    from dronan.db import ping

    result = asyncio.get_event_loop().run_until_complete(ping())
    assert result.get("ok") == 1
