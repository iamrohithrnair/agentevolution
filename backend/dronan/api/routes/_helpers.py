"""Shared serialization helpers for routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from bson import ObjectId
except ImportError:  # pragma: no cover — bson always available via pymongo
    ObjectId = None  # type: ignore[assignment]


def serialise(doc: Any) -> Any:
    """JSON-safe shallow copy.

    Stringifies datetimes / ObjectIds, recurses into dicts and lists, and
    leaves primitive types untouched.
    """
    if isinstance(doc, dict):
        return {k: serialise(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [serialise(v) for v in doc]
    if isinstance(doc, tuple):
        return [serialise(v) for v in doc]
    if isinstance(doc, datetime):
        return doc.isoformat()
    if ObjectId is not None and isinstance(doc, ObjectId):
        return str(doc)
    return doc
