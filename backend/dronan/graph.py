"""LangGraph wiring for Dronan.

`build_graph` returns a compiled ``StateGraph`` whose nodes are the 17
specialists registered in ``backend.dronan.agents``. The graph uses a
checkpointer so a worker crash is recoverable from the last hop.

Two checkpointers are supported:

* ``MongoDBSaver`` (production) — persists every hop to a MongoDB
  collection keyed on ``thread_id``.
* ``InMemorySaver`` (tests / local dev) — pure-python; safe under
  ``mongomock-motor`` which doesn't support all transactional features
  the Mongo saver requires.

The choice is driven by the ``checkpointer`` arg on ``build_graph``.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .agents import AGENTS, SPECIALISTS, MissionState

DEFAULT_RECURSION_LIMIT = 50


def _wrap_with_db(node: Callable[..., Awaitable[dict]], db: Any) -> Callable[..., Awaitable[dict]]:
    """Bind ``db`` into a node's call signature.

    LangGraph nodes are ``(state) -> dict`` but our agent_node decorator
    accepts an optional ``db`` kwarg. We don't want every node to pull
    ``db`` from a context-var, so we curry it in here at compile time.
    """

    async def _runner(state: MissionState) -> dict:
        return await node(state, db=db)

    _runner.__name__ = getattr(node, "__name__", "node")
    return _runner


def build_supervisor(*, db: Any, checkpointer: BaseCheckpointSaver | None = None):
    """Alias for ``build_graph`` — kept for the voice worker's lazy import.

    The LiveKit worker (``dronan.voice.livekit_worker``) imports this name
    lazily so it can fall back cleanly when the graph module is absent. It
    returns the same compiled ``StateGraph`` with the database curried into
    every node.
    """
    return build_graph(db=db, checkpointer=checkpointer)


def build_graph(
    *,
    db: Any,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Compile the StateGraph with the ``db`` curried into every node."""
    g = StateGraph(MissionState)

    # Nodes
    g.add_node("supervisor", _wrap_with_db(AGENTS["supervisor"], db))
    for name in SPECIALISTS:
        g.add_node(name, _wrap_with_db(AGENTS[name], db))

    # Edges
    g.add_edge(START, "supervisor")
    for name in SPECIALISTS:
        g.add_edge(name, "supervisor")

    def _route_from_supervisor(state: MissionState) -> str:
        nxt = state.get("route", "__end__")
        if nxt in (None, "__end__"):
            return END
        return nxt

    g.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {name: name for name in SPECIALISTS} | {END: END},
    )

    saver = checkpointer if checkpointer is not None else InMemorySaver()
    return g.compile(checkpointer=saver)


def make_mongo_saver(client: Any, *, db_name: str = "dronan") -> BaseCheckpointSaver:
    """Construct a production MongoDB-backed checkpointer.

    Imported lazily so unit tests that don't touch real Mongo don't pay
    the import cost (or the connection guards).
    """
    from langgraph.checkpoint.mongodb import MongoDBSaver

    return MongoDBSaver(
        client,
        db_name=db_name,
        checkpoint_collection_name="langgraph_checkpoints",
        writes_collection_name="langgraph_checkpoint_writes",
    )
