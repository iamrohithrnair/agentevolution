"""Audit tool — append-only signature record per mission step.

P2 ships an unencrypted variant; Queryable Encryption lands in P5 alongside
the secrets-management work.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from ._decorator import mongo_tool


@mongo_tool(side_effect_class="audit", agent="AuditAgent")
async def record_signature(
    *,
    db: Any,
    mission_id: str,
    step: str,
    payload: dict,
) -> dict:
    """Append a signature row to ``audit_trail`` for ``mission_id`` / ``step``."""
    blob = repr(sorted(payload.items())).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    now = datetime.now(timezone.utc)
    doc = {
        "mission_id": mission_id,
        "step": step,
        "digest": digest,
        "ts": now,
    }
    await db.audit_trail.insert_one(doc)
    return {"mission_id": mission_id, "step": step, "digest": digest, "ts": now}
