"""Tests for the ``@mongo_tool`` decorator (idempotency + tool_call_log)."""

from __future__ import annotations

import pytest

from backend.dronan.tools._decorator import (
    ToolError,
    make_idempotency_key,
    mongo_tool,
    sha256_hex,
    tool_registry,
)

pytestmark = pytest.mark.unit


def test_make_idempotency_key_explicit_overrides_args() -> None:
    k1 = make_idempotency_key(tool="t", args_hash="abc")
    k2 = make_idempotency_key(tool="t", args_hash="abc", explicit="MED-1:plan")
    assert k1 == "t:abc"
    assert k2 == "t:MED-1:plan"


def test_sha256_hex_stable_across_dict_order() -> None:
    a = sha256_hex({"a": 1, "b": [2, 3], "c": "x"})
    b = sha256_hex({"c": "x", "b": [2, 3], "a": 1})
    assert a == b


async def test_decorator_short_circuits_on_completed(mongo_db) -> None:
    counter = {"n": 0}

    @mongo_tool(side_effect_class="plan")
    async def add_one(*, db, x: int) -> int:
        counter["n"] += 1
        return x + 1

    r1 = await add_one(db=mongo_db, x=10, idempotency_key="k1")
    r2 = await add_one(db=mongo_db, x=10, idempotency_key="k1")
    assert r1 == r2 == 11
    # Body should have run only once.
    assert counter["n"] == 1
    log = await mongo_db.tool_call_log.find_one({"idempotency_key": "add_one:k1"})
    assert log is not None
    assert log["status"] == "completed"
    assert log["result_hash"]


async def test_decorator_records_failures(mongo_db) -> None:
    @mongo_tool()
    async def boom(*, db) -> None:
        raise ToolError("boom")

    with pytest.raises(ToolError):
        await boom(db=mongo_db, idempotency_key="bk")
    log = await mongo_db.tool_call_log.find_one({"idempotency_key": "boom:bk"})
    assert log is not None
    assert log["status"] == "failed"
    assert log["error"] == "boom"


async def test_registry_populated_on_import() -> None:
    # Must include the tools wired in tools/__init__.py
    for name in (
        "compute_route",
        "check_route_safety",
        "vector_search",
        "search_facilities",
        "run_preflight",
    ):
        assert name in tool_registry
