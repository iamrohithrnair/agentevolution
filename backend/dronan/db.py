"""Motor (async) + PyMongo (sync) client factories for MongoDB Atlas.

Honours the same corporate-TLS env vars as backend/atlas_ping.py:
    MONGODB_TLS_CA_FILE, SSL_CERT_FILE, MONGODB_TLS_ALLOW_INVALID
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient

from dronan.config import atlas_uri_from_env, get_settings


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _expand_env_path(raw: str) -> Path:
    s = raw.strip().strip('"').strip("'").strip("`")
    return Path(os.path.expandvars(s)).expanduser()


def mongo_client_kwargs() -> dict:
    kwargs: dict = {"appName": "dronan"}
    if _env_truthy("MONGODB_TLS_ALLOW_INVALID") or _env_truthy("MONGODB_TLS_INSECURE"):
        print(
            "warning: skipping TLS certificate verification (MONGODB_TLS_ALLOW_INVALID) — insecure",
            file=sys.stderr,
        )
        kwargs["tlsAllowInvalidCertificates"] = True
        return kwargs
    ca_path_raw = (
        os.environ.get("MONGODB_TLS_CA_FILE")
        or os.environ.get("MONGO_TLS_CA_FILE")
        or os.environ.get("SSL_CERT_FILE")
    )
    if ca_path_raw:
        ca_path = _expand_env_path(ca_path_raw)
        if ca_path.is_file():
            kwargs["tlsCAFile"] = str(ca_path.resolve())
    return kwargs


def _require_uri() -> str:
    uri = atlas_uri_from_env()
    if not uri:
        raise RuntimeError(
            "Set MONGODB_URI (or MONGODB_ATLAS_URI / ATLAS_CONNECTION_STRING) in .env"
        )
    return uri


@lru_cache(maxsize=1)
def get_motor_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        _require_uri(), serverSelectionTimeoutMS=15_000, **mongo_client_kwargs()
    )


@lru_cache(maxsize=1)
def get_sync_client() -> MongoClient:
    return MongoClient(_require_uri(), serverSelectionTimeoutMS=15_000, **mongo_client_kwargs())


def get_db() -> AsyncIOMotorDatabase:
    return get_motor_client()[get_settings().mongodb_db]


def get_sync_db():
    return get_sync_client()[get_settings().mongodb_db]


async def ping() -> dict:
    return await get_db().command("ping")


# Back-compat alias — API main.py imports ``get_motor_db``.
get_motor_db = get_db
