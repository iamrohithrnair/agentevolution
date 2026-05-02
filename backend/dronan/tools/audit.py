"""Audit tool — append-only signature record per mission step.

The signature format mirrors ``DroneFleet/api/server.py:/api/confirm-delivery``
(``SIG-<sha256[:8]>``) so the operator UI can show a stable short id.

Queryable Encryption (planned in §11) lands as a layered enhancement —
the fields we hash are the same ones a QE-encrypted client would see, so
the digest is forward-compatible.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ._decorator import mongo_tool


def _stable_blob(payload: dict) -> bytes:
    """Stable JSON encoding for hashing — sort keys, use canonical separators."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )


def signature_id(payload: dict, *, ts: datetime | None = None) -> str:
    """Compute the public ``SIG-<8>`` id from ``payload`` (+ optional timestamp).

    Pure function so callers can pre-compute the id before persisting.
    """
    blob = _stable_blob(payload)
    if ts is not None:
        blob += b"|" + ts.isoformat().encode("utf-8")
    return "SIG-" + hashlib.sha256(blob).hexdigest()[:8]


@mongo_tool(side_effect_class="audit", agent="AuditAgent")
async def record_signature(
    *,
    db: Any,
    mission_id: str,
    step: str,
    payload: dict,
) -> dict:
    """Append a signature row to ``audit_trail`` for ``mission_id`` / ``step``.

    Returns ``{mission_id, step, digest, signature_id, ts}`` where
    ``signature_id`` is the DroneFleet-style ``SIG-<8>`` short id.
    """
    blob = _stable_blob(payload)
    digest = hashlib.sha256(blob).hexdigest()
    now = datetime.now(timezone.utc)
    sig_id = signature_id(payload, ts=now)
    doc = {
        "mission_id": mission_id,
        "step": step,
        "digest": digest,
        "signature_id": sig_id,
        "ts": now,
    }
    await db.audit_trail.insert_one(doc)
    return {
        "mission_id": mission_id,
        "step": step,
        "digest": digest,
        "signature_id": sig_id,
        "ts": now,
    }
