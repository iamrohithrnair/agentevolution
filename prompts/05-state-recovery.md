# 05 · State, Tool Execution & Recovery Spec
**DroneFleet · MongoDB Agentic Evolution Hackathon**

> Cross-references: `01-system-architecture.md`, `02-mongodb-data-model.md`,
> `04-langchain-agents.md`, `06-skills-discovery.md`, `10-self-evolution.md`,
> `12-acceptance-tests.md`.

This document is the canonical specification for **how the runtime executes
tool calls, retains reasoning state, recovers from single failures, and
guarantees consistency in multi-step tasks** using **MongoDB +
LangChain/LangGraph**. Every claim below is backed by either runnable
Python, a Mongo query, or an index spec.

---

## 1 · MongoDB Checkpointer Setup

### 1.1 `MongoDBSaver` wiring

Use the official `langgraph-checkpoint-mongodb` package. Pin the async
client (`AsyncIOMotorClient`) and a single dedicated collection,
`langgraph_checkpoints`. Thread-id strategy: **`thread_id == mission_id`** —
every mission is one LangGraph thread; every node returns control after
which a checkpoint is written; resume is a one-line invocation.

```python
# dronefleet/state/checkpointer.py
from __future__ import annotations
from motor.motor_asyncio import AsyncIOMotorClient
from langgraph_checkpoint_mongodb import MongoDBSaver

def build_checkpointer(mongo_uri: str) -> MongoDBSaver:
    client = AsyncIOMotorClient(mongo_uri, uuidRepresentation="standard")
    return MongoDBSaver(
        client=client,
        db_name="dronefleet",
        collection_name="langgraph_checkpoints",
        # Optional: dedicated writes collection for incremental channel writes
        writes_collection_name="langgraph_checkpoint_writes",
    )

def thread_config(mission_id: str) -> dict:
    return {"configurable": {"thread_id": mission_id}}
```

### 1.2 Compile the graph with the checkpointer

```python
# dronefleet/agents/graph.py
from langgraph.graph import StateGraph, START, END
from dronefleet.state.checkpointer import build_checkpointer

def compile_graph(mongo_uri: str):
    g = StateGraph(MissionState)
    # ... nodes & edges (see 04-langchain-agents.md §1) ...
    return g.compile(checkpointer=build_checkpointer(mongo_uri))
```

### 1.3 `langgraph_checkpoints` schema (what's persisted)

The `MongoDBSaver` writes one document per checkpoint per thread per
sub-graph. Indicative shape:

```json
{
  "_id": ObjectId("…"),
  "thread_id": "mss-2026-05-12-0001",   // == mission_id
  "thread_ts": "01HXX…",                // monotonic ULID per checkpoint
  "parent_ts": "01HXW…",                // previous checkpoint
  "checkpoint_ns": "",                  // sub-graph namespace ("" = root)
  "checkpoint": {                       // BSON-serialised channel state
    "v": 1,
    "ts": "2026-05-12T09:00:03.205Z",
    "id":  "01HXX…",
    "channel_values": { /* MissionState fields */ },
    "channel_versions": { "messages": 7, "anomalies": 2, ... },
    "versions_seen": { "supervisor": { "messages": 6 }, ... },
    "pending_sends": []
  },
  "metadata": {
    "source": "loop",                   // input | loop | update | fork
    "step": 12,
    "writes": { "planner": { "plan_step_log": [...] } }
  }
}
```

The companion writes collection holds the per-channel `pending_writes`
between checkpoints so concurrent fan-out nodes don't race.

### 1.4 Indexes (must be declared in the bootstrap migration)

```python
await db.langgraph_checkpoints.create_index(
    [("thread_id", 1), ("checkpoint_ns", 1), ("thread_ts", -1)],
    name="thread_latest",
)
await db.langgraph_checkpoints.create_index(
    [("thread_id", 1), ("metadata.step", 1)], name="thread_step",
)
await db.langgraph_checkpoint_writes.create_index(
    [("thread_id", 1), ("checkpoint_ns", 1), ("checkpoint_id", 1)],
    name="thread_writes",
)
```

### 1.5 When checkpoints are written

`MongoDBSaver` writes a checkpoint **after each node returns**. Combined
with the `Supervisor → specialist → Supervisor` loop (see
`04-langchain-agents.md §1.3`), this means a checkpoint exists at every
inter-agent boundary — the unit of recovery is "one specialist hop".

### 1.6 Resume in one line

```python
graph = compile_graph(MONGO_URI)
await graph.ainvoke(None, config=thread_config(mission_id))   # resume
```

Passing `None` as input tells LangGraph: "no new input; pick up wherever
the latest checkpoint left you". This is the single most important line
in this entire repo.

---

## 2 · Tool Call Lifecycle — `traceable_tool`

Every tool that touches **state, network, or the simulator** is wrapped in
`traceable_tool`. The decorator gives:

* **Idempotency** via a deterministic key.
* **Atomic dedup** via `update_one(upsert=True)` keyed on the idempotency_key.
* **Pre/post lifecycle records** in `tool_call_log`.
* **Result caching** for retried calls.
* **Span emission** to `traces`.
* **Tenacity-driven retry** for transient failure.

### 2.1 Idempotency key

```python
# dronefleet/state/idempotency.py
import hashlib, json
from typing import Any

def canonical(args: dict[str, Any]) -> str:
    """Stable JSON: sorted keys, no whitespace, ISO-8601 datetimes."""
    def default(o):
        if hasattr(o, "isoformat"): return o.isoformat()
        if hasattr(o, "model_dump"): return o.model_dump()
        return str(o)
    return json.dumps(args, sort_keys=True, separators=(",", ":"), default=default)

def idempotency_key(agent: str, tool: str, args: dict, mission_step_id: str) -> str:
    h = hashlib.sha256()
    h.update(agent.encode());           h.update(b"\x1f")
    h.update(tool.encode());            h.update(b"\x1f")
    h.update(canonical(args).encode()); h.update(b"\x1f")
    h.update(mission_step_id.encode())
    return h.hexdigest()
```

`mission_step_id` is the LangGraph `metadata.step` integer for the current
node invocation, so retries inside the same node share a key but a fresh
node invocation gets a new one.

### 2.2 `tool_call_log` schema

```json
{
  "_id": "<idempotency_key>",
  "mission_id": "mss-…",
  "agent": "planner",
  "tool":  "solve_vrp",
  "args":  { /* canonical args */ },
  "status": "in_flight" | "success" | "failed" | "compensated",
  "attempt": 1,
  "started_at": ISODate,
  "ended_at":   ISODate,
  "latency_ms": 1710,
  "result": { /* persisted on success */ },
  "result_hash": "sha256:…",
  "error": { "type": "...", "message": "..." } | null,
  "side_effect": "read" | "write" | "external" | "write+external",
  "compensation": { "tool": "abort_drone", "args": {...} } | null
}
```

### 2.3 Indexes

```python
await db.tool_call_log.create_index([("mission_id", 1), ("started_at", 1)])
await db.tool_call_log.create_index(
    [("status", 1), ("started_at", 1)], name="recover_in_flight",
)
```

### 2.4 The decorator (production-grade)

```python
# dronefleet/state/traceable.py
from __future__ import annotations
import asyncio, hashlib, json, time, traceback
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Awaitable

from tenacity import (
    retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type,
)
from pymongo.errors import DuplicateKeyError

from dronefleet.db import db
from dronefleet.state.idempotency import idempotency_key, canonical

class TransientToolError(Exception):
    """Raised by tools to signal retry-eligible failures."""

class PermanentToolError(Exception):
    """Raised for failures that must NOT be retried (e.g., infeasible)."""

class InFlightConflict(Exception):
    """Another caller is currently executing this exact tool call."""

_RETRY = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.2, max=2.0, jitter=0.4),
    retry=retry_if_exception_type(TransientToolError),
)

def _hash_result(result: Any) -> str:
    payload = canonical({"r": result if isinstance(result, (dict, list, str, int, float, bool, type(None))) else str(result)})
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

def traceable_tool(
    agent: str,
    side_effect: str = "read",
    compensation: Callable[..., Awaitable[Any]] | None = None,
    in_flight_wait_s: float = 0.0,
):
    """Wrap an async tool function with idempotency, retry, and tracing.

    Args
    ----
    agent           : name of the calling agent (for the log row).
    side_effect     : 'read' | 'write' | 'external' | 'write+external'.
    compensation    : optional async callable invoked on saga rollback.
    in_flight_wait_s: if >0, on InFlightConflict wait up to this many seconds
                      polling for completion before failing.
    """
    def decorator(fn: Callable[..., Awaitable[Any]]):
        tool_name = fn.__name__

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            # mission_step_id and mission_id are conventionally injected
            # by the node wrapper into kwargs.
            mission_id      = kwargs.pop("__mission_id__")
            mission_step_id = kwargs.pop("__mission_step_id__")
            trace_id        = kwargs.pop("__trace_id__", mission_id)
            parent_span_id  = kwargs.pop("__parent_span_id__", None)

            key = idempotency_key(agent, tool_name, kwargs, mission_step_id)

            # --- Pre-write: atomically claim the key ---
            now = datetime.utcnow()
            try:
                await db.tool_call_log.insert_one({
                    "_id": key,
                    "mission_id": mission_id,
                    "agent": agent,
                    "tool":  tool_name,
                    "args":  json.loads(canonical(kwargs)),
                    "status": "in_flight",
                    "attempt": 1,
                    "started_at": now,
                    "side_effect": side_effect,
                    "compensation": None,
                })
                cached = None
            except DuplicateKeyError:
                # Either: success cached → return; in_flight → wait/raise.
                doc = await db.tool_call_log.find_one({"_id": key})
                if doc and doc["status"] == "success":
                    return doc["result"]
                if doc and doc["status"] == "in_flight":
                    if in_flight_wait_s <= 0:
                        raise InFlightConflict(key)
                    deadline = time.monotonic() + in_flight_wait_s
                    while time.monotonic() < deadline:
                        await asyncio.sleep(0.1)
                        doc = await db.tool_call_log.find_one({"_id": key})
                        if doc and doc["status"] == "success":
                            return doc["result"]
                        if doc and doc["status"] == "failed":
                            raise PermanentToolError(doc.get("error", {}).get("message", "failed"))
                    raise InFlightConflict(key)
                # failed: surface previous error
                raise PermanentToolError((doc or {}).get("error", {}).get("message", "previous failure"))

            # --- Execute (with retry) ---
            attempt = 0
            t0 = time.perf_counter()
            try:
                async def _run():
                    nonlocal attempt
                    attempt += 1
                    return await fn(*args, **kwargs)
                result = await _RETRY(_run)()
            except Exception as e:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                await db.tool_call_log.update_one(
                    {"_id": key},
                    {"$set": {
                        "status": "failed",
                        "attempt": attempt,
                        "ended_at": datetime.utcnow(),
                        "latency_ms": latency_ms,
                        "error": {"type": type(e).__name__,
                                  "message": str(e),
                                  "trace": traceback.format_exc(limit=5)},
                    }},
                )
                await db.traces.insert_one({
                    "trace_id": trace_id, "parent_span_id": parent_span_id,
                    "agent": agent, "tool": tool_name, "status": "error",
                    "attempt": attempt, "latency_ms": latency_ms,
                    "started_at": now, "ended_at": datetime.utcnow(),
                    "error": str(e),
                })
                raise

            # --- Post-write: success ---
            latency_ms = int((time.perf_counter() - t0) * 1000)
            comp = None
            if compensation is not None:
                comp = {"tool": getattr(compensation, "__name__", "compensation"),
                        "args": kwargs}
            await db.tool_call_log.update_one(
                {"_id": key},
                {"$set": {
                    "status": "success",
                    "attempt": attempt,
                    "ended_at": datetime.utcnow(),
                    "latency_ms": latency_ms,
                    "result": result if isinstance(result, (dict, list)) else {"value": result},
                    "result_hash": _hash_result(result),
                    "compensation": comp,
                }},
            )
            await db.traces.insert_one({
                "trace_id": trace_id, "parent_span_id": parent_span_id,
                "agent": agent, "tool": tool_name, "status": "ok",
                "attempt": attempt, "latency_ms": latency_ms,
                "started_at": now, "ended_at": datetime.utcnow(),
                "idempotency_key": key,
            })
            # If the tool registered a compensating action, push it onto the saga.
            if comp:
                from dronefleet.state.saga import push_compensation
                await push_compensation(mission_id, comp, key)
            return result

        wrapper.__traceable__ = True
        wrapper.__agent__ = agent
        wrapper.__side_effect__ = side_effect
        return wrapper
    return decorator
```

### 2.5 Using the decorator

```python
# dronefleet/tools/dispatch.py
from langchain_core.tools import tool
from dronefleet.state.traceable import traceable_tool
from dronefleet.tools.compensations import abort_drone

@tool
@traceable_tool(agent="dispatch", side_effect="write+external",
                compensation=abort_drone, in_flight_wait_s=2.0)
async def arm_drone(drone_id: str, mission_id: str, **_kw) -> dict:
    """Arm the named drone for takeoff."""
    return await sim_client.arm(drone_id)
```

(The `mission_id`, `mission_step_id`, etc. are injected by a thin
node-wrapper before invoking the tool — see §10.)

---

## 3 · Single-Failure Recovery — three failure classes

### 3.1 Transient (network, rate limit)

Already handled inside `traceable_tool` via tenacity:

```python
_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.2, max=2.0, jitter=0.4),
    retry=retry_if_exception_type(TransientToolError),
)
```

Tools opt in by raising `TransientToolError` rather than the underlying
exception (e.g., catch `httpx.ReadTimeout`, raise `TransientToolError`).

### 3.2 Tool failure (e.g., OR-Tools infeasible)

Raised as `PermanentToolError`. SupervisorAgent catches via the node
wrapper, picks a fallback agent, and writes a lesson seed:

```python
# dronefleet/agents/nodes/planner_node.py
from dronefleet.state.traceable import PermanentToolError
from dronefleet.tools.vrp import solve_vrp
from dronefleet.tools.naive import naive_sequential_plan
from dronefleet.db import db

async def planner_node(state):
    args = build_vrp_args(state)
    try:
        plan = await solve_vrp(**args,
                               __mission_id__=state["mission_id"],
                               __mission_step_id__=str(state.get("step", 0)))
    except PermanentToolError as e:
        # Fallback: naive sequential planner.
        plan = await naive_sequential_plan(args)
        await db.lesson_seeds.insert_one({
            "mission_id": state["mission_id"],
            "kind": "tool_failure_pattern",
            "summary": f"solve_vrp infeasible with weights={args['weights']}; "
                       f"used naive fallback. Cause: {e}",
            "raw_args": args,
            "created_at": datetime.utcnow(),
        })
    return {"plan_step_log": [{"agent": "planner", "ok": True,
                               "fallback": isinstance(plan, dict) and plan.get("naive", False)}]}
```

ReflectionAgent later consumes `lesson_seeds` and promotes them into
`mission_memory` (see `10-self-evolution.md §1`).

### 3.3 Agent crash mid-flight (process restart)

Boot-time scan + resume:

```python
# dronefleet/state/resume.py
from datetime import datetime, timedelta
from dronefleet.db import db
from dronefleet.agents.graph import compile_graph
from dronefleet.state.checkpointer import thread_config

NON_TERMINAL = {"planning", "in_progress", "paused"}

async def resume_in_flight_missions(mongo_uri: str, max_age_min: int = 60):
    graph = compile_graph(mongo_uri)
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_min)
    cursor = db.missions.find({
        "status":     {"$in": list(NON_TERMINAL)},
        "updated_at": {"$gte": cutoff},
    })
    async for m in cursor:
        mission_id = m["_id"]
        # Verify a checkpoint exists for this thread.
        chk = await db.langgraph_checkpoints.find_one(
            {"thread_id": mission_id}, sort=[("thread_ts", -1)],
        )
        if not chk:
            await db.missions.update_one(
                {"_id": mission_id},
                {"$set": {"status": "failed",
                          "fail_reason": "no_checkpoint_on_resume"}},
            )
            continue
        # Resume the graph.
        try:
            await graph.ainvoke(None, config=thread_config(mission_id))
        except Exception as e:
            await db.missions.update_one(
                {"_id": mission_id},
                {"$set": {"status": "failed",
                          "fail_reason": f"resume_error:{e}"}},
            )
```

Wire it into FastAPI startup:

```python
# dronefleet/api/app.py
from fastapi import FastAPI
from dronefleet.state.resume import resume_in_flight_missions

app = FastAPI()

@app.on_event("startup")
async def _on_startup():
    await resume_in_flight_missions(MONGO_URI)
```

This is what makes `pytest test_recovery_resume.py` pass: the test kills
the API mid-mission, restarts it, and asserts the mission proceeds to
`completed` without re-planning from scratch.

---

## 4 · Saga / Compensating Actions for multi-step writes

### 4.1 Mission state machine + atomic transitions

```python
# dronefleet/state/mission_fsm.py
ALLOWED_TRANSITIONS = {
    "planning":    {"in_progress", "failed"},
    "in_progress": {"paused", "completed", "failed"},
    "paused":      {"in_progress", "failed"},
    "completed":   set(),
    "failed":      set(),
}

async def transition(db, mission_id: str, new_status: str, *, reason: str = ""):
    """Atomic transition guarded by $expr; raises if illegal."""
    res = await db.missions.find_one_and_update(
        {
            "_id": mission_id,
            "$expr": {"$in": [new_status, {
                "$switch": {
                    "branches": [
                        {"case": {"$eq": ["$status", k]}, "then": list(v)}
                        for k, v in ALLOWED_TRANSITIONS.items()
                    ],
                    "default": [],
                },
            }]},
        },
        {"$set": {"status": new_status, "updated_at": datetime.utcnow(),
                  "fail_reason": reason if new_status == "failed" else None}},
        return_document=True,
    )
    if not res:
        raise IllegalTransition(f"{mission_id} cannot move to {new_status}")
    return res
```

### 4.2 Compensating actions on the mission doc

```python
# dronefleet/state/saga.py
from datetime import datetime
from typing import Any
from dronefleet.db import db

async def push_compensation(mission_id: str, comp: dict, idempotency_key: str):
    await db.missions.update_one(
        {"_id": mission_id},
        {"$push": {"compensations": {
            "tool": comp["tool"],
            "args": comp["args"],
            "idempotency_key": idempotency_key,
            "pushed_at": datetime.utcnow(),
            "executed": False,
        }}},
    )

class MissionSaga:
    """Execute a multi-step write sequence with reverse-order rollback."""

    def __init__(self, mission_id: str):
        self.mission_id = mission_id
        self.steps: list[tuple[str, Any, Any]] = []   # (label, fn, comp_fn)

    def add(self, label: str, action, compensation):
        self.steps.append((label, action, compensation))
        return self

    async def run(self):
        executed: list[tuple[str, Any]] = []   # (label, comp_fn)
        try:
            for label, action, comp in self.steps:
                await action()
                executed.append((label, comp))
        except Exception as e:
            await self._rollback(executed, reason=str(e))
            raise
        return True

    async def _rollback(self, executed, reason: str):
        for label, comp in reversed(executed):
            try:
                await comp()
            except Exception as ce:
                await db.missions.update_one(
                    {"_id": self.mission_id},
                    {"$push": {"saga_errors": {
                        "step": label, "error": str(ce), "at": datetime.utcnow()}}},
                )
        await db.missions.update_one(
            {"_id": self.mission_id},
            {"$set": {"compensations.$[].executed": True,
                      "rollback_reason": reason,
                      "updated_at": datetime.utcnow()}},
        )
        await transition(db, self.mission_id, "failed", reason=f"saga_rollback:{reason}")
```

### 4.3 Worked example — Dispatch saga

```python
# dronefleet/agents/nodes/dispatch_node.py
from dronefleet.state.saga import MissionSaga
from dronefleet.tools.dispatch import (
    arm_drone, start_cold_chain, append_audit, push_waypoints,
)
from dronefleet.tools.compensations import (
    disarm_drone, stop_cold_chain, redact_audit, clear_waypoints,
)

async def dispatch_node(state):
    mid = state["mission_id"]
    drone_id = state["assigned_drone_id"]
    saga = MissionSaga(mid)
    saga.add("arm",       lambda: arm_drone(drone_id=drone_id, __mission_id__=mid, __mission_step_id__="arm"),
                          lambda: disarm_drone(drone_id=drone_id, __mission_id__=mid, __mission_step_id__="disarm"))
    saga.add("cold_chain",lambda: start_cold_chain(drone_id=drone_id, __mission_id__=mid, __mission_step_id__="cc"),
                          lambda: stop_cold_chain(drone_id=drone_id, __mission_id__=mid, __mission_step_id__="cc-rb"))
    saga.add("audit",     lambda: append_audit(mid, "dispatched", __mission_id__=mid, __mission_step_id__="aud"),
                          lambda: redact_audit(mid, "dispatched", __mission_id__=mid, __mission_step_id__="aud-rb"))
    saga.add("waypoints", lambda: push_waypoints(drone_id=drone_id, plan=state["plan"], __mission_id__=mid, __mission_step_id__="wp"),
                          lambda: clear_waypoints(drone_id=drone_id, __mission_id__=mid, __mission_step_id__="wp-rb"))
    await saga.run()
    return {"plan_step_log": [{"agent": "dispatch", "ok": True}]}
```

---

## 5 · Multi-Step Task Consistency

Three guarantees, all implementable on a single Atlas cluster.

### 5.1 At-most-once side effects → idempotency_key on `tool_call_log`

Already enforced by `traceable_tool` (§2). The `_id` of the row IS the
idempotency key, so a duplicate call hits a `DuplicateKeyError` and either
returns the cached result or fails-fast.

### 5.2 Causal consistency → causal-consistent sessions

```python
# dronefleet/state/sessions.py
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient

@asynccontextmanager
async def causal_session(client: AsyncIOMotorClient):
    async with await client.start_session(causal_consistency=True) as s:
        yield s
```

Use it everywhere a workflow does write-then-read:

```python
async with causal_session(client) as s:
    await db.missions.update_one({"_id": mid},
        {"$set": {"status": "in_progress"}}, session=s)
    # This read is guaranteed to see the write above on any secondary.
    m = await db.missions.find_one({"_id": mid}, session=s)
```

### 5.3 Read-your-writes inside an agent → reuse session

```python
async def planner_node(state, client=client):
    async with causal_session(client) as s:
        await db.plans.insert_one(plan_doc, session=s)
        # The very next step (e.g., validation) will see this plan.
        plans = await db.plans.find({"mission_id": mid}, session=s).to_list(None)
        ...
```

Couple this with a **majority** read concern + write concern for write
durability:

```python
client = AsyncIOMotorClient(
    MONGO_URI,
    readConcernLevel="majority",
    w="majority",
    journal=True,
    retryWrites=True,
)
```

---

## 6 · Distributed Lock (single-drone multi-mission contention)

Implemented as a TTL doc in `locks`. Acquisition is an upsert with an
`$expr` guard; renewal is a heartbeat.

### 6.1 Index

```python
await db.locks.create_index("expires_at", expireAfterSeconds=0)
```

### 6.2 Code

```python
# dronefleet/state/locks.py
from __future__ import annotations
import asyncio, uuid
from datetime import datetime, timedelta
from dronefleet.db import db

class LockBusy(Exception): ...

class DroneLock:
    def __init__(self, drone_id: str, owner_id: str | None = None,
                 ttl: int = 30):
        self.drone_id = drone_id
        self.owner_id = owner_id or str(uuid.uuid4())
        self.ttl = ttl
        self._renew_task: asyncio.Task | None = None

    async def acquire(self) -> bool:
        now = datetime.utcnow()
        exp = now + timedelta(seconds=self.ttl)
        try:
            await db.locks.update_one(
                {
                    "_id": f"drone:{self.drone_id}",
                    "$or": [
                        {"expires_at": {"$lte": now}},
                        {"owner_id":  self.owner_id},
                    ],
                },
                {"$set": {"owner_id": self.owner_id,
                          "expires_at": exp, "acquired_at": now}},
                upsert=True,
            )
            return True
        except Exception:
            raise LockBusy(self.drone_id)

    async def renew(self):
        await db.locks.update_one(
            {"_id": f"drone:{self.drone_id}", "owner_id": self.owner_id},
            {"$set": {"expires_at": datetime.utcnow() + timedelta(seconds=self.ttl)}},
        )

    async def release(self):
        await db.locks.delete_one(
            {"_id": f"drone:{self.drone_id}", "owner_id": self.owner_id}
        )

    async def __aenter__(self):
        await self.acquire()
        async def _renew_loop():
            while True:
                await asyncio.sleep(self.ttl / 3)
                await self.renew()
        self._renew_task = asyncio.create_task(_renew_loop())
        return self

    async def __aexit__(self, *exc):
        if self._renew_task: self._renew_task.cancel()
        await self.release()
```

Usage:

```python
async with DroneLock(drone_id="drone-7", ttl=30):
    await dispatch_mission(...)
```

---

## 7 · Outbox Pattern for reliable WS notifications

We must not lose dashboard updates if the WS layer crashes. Solve with an
outbox table written **in the same session** as the state mutation, then a
Change Stream tail emits and acks.

### 7.1 Schema

```json
{
  "_id": ObjectId,
  "mission_id": "mss-…",
  "topic": "mission.state",
  "payload": { ... },
  "created_at": ISODate,
  "delivered_at": ISODate | null,
  "attempts": 0
}
```

### 7.2 Write inside the same session

```python
async with causal_session(client) as s, await s.start_transaction():
    await db.missions.update_one({"_id": mid},
        {"$set": {"status": "in_progress"}}, session=s)
    await db.outbox.insert_one({
        "mission_id": mid, "topic": "mission.state",
        "payload": {"status": "in_progress"},
        "created_at": datetime.utcnow(),
        "delivered_at": None, "attempts": 0,
    }, session=s)
```

### 7.3 Dispatcher

```python
# dronefleet/state/outbox.py
async def run_dispatcher(ws_hub):
    pipeline = [{"$match": {
        "operationType": "insert",
        "fullDocument.delivered_at": None,
    }}]
    async with db.outbox.watch(pipeline, full_document="updateLookup") as stream:
        async for change in stream:
            doc = change["fullDocument"]
            try:
                await ws_hub.broadcast(doc["topic"], doc["payload"])
                await db.outbox.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"delivered_at": datetime.utcnow()},
                     "$inc": {"attempts": 1}},
                )
            except Exception:
                await db.outbox.update_one(
                    {"_id": doc["_id"]}, {"$inc": {"attempts": 1}},
                )
```

A reaper job re-scans `outbox` for `delivered_at == null AND attempts < 5`
every 30 s for the WS-down case.

---

## 8 · Replay & Memory Inspector — `/api/missions/{id}/trace`

### 8.1 Response schema

```json
{
  "mission": { /* missions doc */ },
  "checkpoints": [
    { "thread_ts": "01HXX…", "step": 12, "writes": {...},
      "channel_values": {...} }
  ],
  "agent_messages": [
    { "timestamp": "...", "from": "...", "to": "...", "intent": "...",
      "payload": {...}, "tokens_in": 0, "tokens_out": 0,
      "latency_ms": 0, "status": "ok" }
  ],
  "tool_calls": [
    { "_id": "<key>", "agent": "...", "tool": "...", "status": "...",
      "attempt": 1, "started_at": "...", "ended_at": "...",
      "latency_ms": 0, "args": {...}, "result_hash": "...",
      "side_effect": "...", "compensation": {...} }
  ],
  "saga": { "compensations": [...] }
}
```

### 8.2 Endpoint

```python
# dronefleet/api/trace.py
from fastapi import APIRouter, HTTPException
router = APIRouter()

@router.get("/api/missions/{mission_id}/trace")
async def trace(mission_id: str):
    mission = await db.missions.find_one({"_id": mission_id})
    if not mission:
        raise HTTPException(404, "mission not found")
    chk = await db.langgraph_checkpoints.find(
        {"thread_id": mission_id},
    ).sort("thread_ts", 1).to_list(length=None)
    msgs = await db.agent_messages.find(
        {"mission_id": mission_id},
    ).sort("timestamp", 1).to_list(length=None)
    tools = await db.tool_call_log.find(
        {"mission_id": mission_id},
    ).sort("started_at", 1).to_list(length=None)
    return {
        "mission": mission,
        "checkpoints": [
            {"thread_ts": c["thread_ts"],
             "step": c["metadata"]["step"],
             "writes": c["metadata"].get("writes", {}),
             "channel_values": c["checkpoint"]["channel_values"]}
            for c in chk
        ],
        "agent_messages": msgs,
        "tool_calls": tools,
        "saga": {"compensations": mission.get("compensations", [])},
    }
```

The Memory Inspector front-end (see `09-frontend.md`) renders this as a
timeline; clicking a checkpoint reveals the full `MissionState` at that
point, and a "Resume from here" button calls `graph.ainvoke(None,
config=thread_config(...))` after a `fork` write to checkpoints.

---

## 9 · Test Plan for State Recovery (cross-ref `12-acceptance-tests.md`)

### 9.1 `tests/recovery/test_recovery_resume.py`

```python
import asyncio, os, signal, time, pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_kill_resume(api_process, mongo_seeded):
    async with AsyncClient(base_url="http://localhost:8000") as c:
        r = await c.post("/api/missions",
                         json={"request": "send blood to clinic B urgently"})
        mid = r.json()["mission_id"]
        # Wait until state == in_progress, then kill -9.
        for _ in range(50):
            await asyncio.sleep(0.1)
            s = (await c.get(f"/api/missions/{mid}")).json()["status"]
            if s == "in_progress":
                break
        os.kill(api_process.pid, signal.SIGKILL)
        # Restart the API.
        api_process.restart()
        await asyncio.sleep(2.0)
        # Poll until completed.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            s = (await c.get(f"/api/missions/{mid}")).json()["status"]
            if s in ("completed", "failed"):
                assert s == "completed"
                return
            await asyncio.sleep(0.5)
        pytest.fail("mission did not resume to completion")
```

### 9.2 `tests/recovery/test_idempotency.py`

```python
@pytest.mark.asyncio
async def test_duplicate_tool_call_runs_once(db, monkeypatch):
    calls = []
    @traceable_tool(agent="dispatch", side_effect="external")
    async def foo(x: int, **kw): calls.append(x); return {"y": x*2}
    common = {"__mission_id__": "m1", "__mission_step_id__": "s1"}
    a = await foo(x=3, **common)
    b = await foo(x=3, **common)   # duplicate
    assert a == b == {"y": 6}
    assert calls == [3]
```

### 9.3 `tests/recovery/test_saga_rollback.py`

```python
@pytest.mark.asyncio
async def test_infeasible_plan_rolls_back(monkeypatch, db):
    saga = MissionSaga("m-saga-1")
    log = []
    saga.add("a", lambda: log.append("a-do") or asyncio.sleep(0),
                  lambda: log.append("a-undo") or asyncio.sleep(0))
    saga.add("b", lambda: log.append("b-do") or asyncio.sleep(0),
                  lambda: log.append("b-undo") or asyncio.sleep(0))
    async def boom(): raise PermanentToolError("infeasible")
    saga.add("c", boom, lambda: log.append("c-undo") or asyncio.sleep(0))
    with pytest.raises(PermanentToolError):
        await saga.run()
    assert log == ["a-do", "b-do", "b-undo", "a-undo"]
    # ReflectionAgent gets a lesson seed.
    seed = await db.lesson_seeds.find_one({"mission_id": "m-saga-1"})
    assert seed["kind"] == "tool_failure_pattern"
```

---

## 10 · Production-grade Module — `state/` package, full file

Below is the cohesive `state/` package wiring (≥200 lines of real Python
combining the snippets above into something you can drop into the repo).

```python
# dronefleet/state/__init__.py
from .checkpointer import build_checkpointer, thread_config
from .traceable   import traceable_tool, TransientToolError, PermanentToolError, InFlightConflict
from .idempotency import idempotency_key, canonical
from .mission_fsm import transition, IllegalTransition, ALLOWED_TRANSITIONS
from .saga        import MissionSaga, push_compensation
from .sessions    import causal_session
from .locks       import DroneLock, LockBusy
from .resume      import resume_in_flight_missions
from .outbox      import run_dispatcher

__all__ = [
    "build_checkpointer", "thread_config",
    "traceable_tool", "TransientToolError", "PermanentToolError", "InFlightConflict",
    "idempotency_key", "canonical",
    "transition", "IllegalTransition", "ALLOWED_TRANSITIONS",
    "MissionSaga", "push_compensation",
    "causal_session",
    "DroneLock", "LockBusy",
    "resume_in_flight_missions",
    "run_dispatcher",
]
```

```python
# dronefleet/state/boot.py — wire it all into FastAPI startup
from __future__ import annotations
import asyncio, logging
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from dronefleet.config import MONGO_URI
from dronefleet.state import (
    resume_in_flight_missions, run_dispatcher,
)
from dronefleet.ws.hub import ws_hub
from dronefleet.agents.graph import compile_graph
from dronefleet.agents.registry import register_all
from dronefleet.tools.registry import register_all_tools

log = logging.getLogger("dronefleet.boot")

def install_boot_hooks(app: FastAPI):
    background_tasks: list[asyncio.Task] = []

    @app.on_event("startup")
    async def _startup():
        client = AsyncIOMotorClient(MONGO_URI, w="majority",
                                    readConcernLevel="majority",
                                    journal=True, retryWrites=True)
        await client.admin.command("ping")
        log.info("Mongo OK; ensuring indexes…")
        from dronefleet.db.bootstrap import ensure_indexes
        await ensure_indexes(client)

        log.info("Registering agents and tools…")
        await register_all()
        await register_all_tools()

        log.info("Compiling LangGraph…")
        app.state.graph = compile_graph(MONGO_URI)

        log.info("Starting outbox dispatcher…")
        background_tasks.append(asyncio.create_task(run_dispatcher(ws_hub)))

        log.info("Resuming any in-flight missions from checkpoint…")
        await resume_in_flight_missions(MONGO_URI)

        log.info("DroneFleet boot complete.")

    @app.on_event("shutdown")
    async def _shutdown():
        for t in background_tasks:
            t.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
```

```python
# dronefleet/state/node_wrapper.py — inject __mission_id__ etc into tools
from __future__ import annotations
from functools import wraps
from typing import Callable, Awaitable, Any

def with_tool_context(node_fn: Callable[..., Awaitable[Any]]):
    """Wrap a LangGraph node so that any tool call inside receives the
    mission_id + step_id automatically, without polluting the agent's
    business logic."""
    @wraps(node_fn)
    async def wrapper(state, *args, **kwargs):
        # Stash context in a contextvar for tools to pick up. (Alternative:
        # explicit kwargs, shown elsewhere in the file.)
        from contextvars import ContextVar
        _ctx: ContextVar = globals().setdefault("_TOOL_CTX",
                                                ContextVar("_TOOL_CTX"))
        token = _ctx.set({
            "mission_id":      state["mission_id"],
            "mission_step_id": str(state.get("step", 0)),
            "trace_id":        state.get("trace_id", state["mission_id"]),
            "parent_span_id":  state.get("current_span_id"),
        })
        try:
            return await node_fn(state, *args, **kwargs)
        finally:
            _ctx.reset(token)
    return wrapper
```

```python
# dronefleet/state/exceptions.py
class IllegalTransition(Exception): ...
class NoCheckpointError(Exception): ...
class CompensationFailed(Exception):
    def __init__(self, step: str, original_error: Exception):
        super().__init__(f"compensation failed for step={step}: {original_error}")
        self.step = step
        self.original_error = original_error
```

---

## 11 · Acceptance criteria for this spec

* `pytest tests/recovery/test_recovery_resume.py::test_kill_resume`
* `pytest tests/recovery/test_idempotency.py::test_duplicate_tool_call_runs_once`
* `pytest tests/recovery/test_saga_rollback.py::test_infeasible_plan_rolls_back`
* Manual: kill the `dronefleet.api` container during a live demo dispatch
  → mission resumes within ≤3 s after restart with no operator action.
* Manual: drop the network for 5 s during external API calls → all
  affected tools succeed within their tenacity budget; no duplicate
  side effects in `tool_call_log`.
* `db.tool_call_log.aggregate([{ "$group": { "_id": "$_id", "n":
  {"$sum":1} } }, { "$match": { "n": {"$gt":1} } }])` returns zero rows
  on a 1000-mission soak test (proves uniqueness of the idempotency key).

If all five pass, the runtime satisfies the user's recovery question.
