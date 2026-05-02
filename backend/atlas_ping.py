"""Smoke-test MongoDB Atlas from Python (GenAI-Showcase MongoClient + URI usage).

Optional env for corporate TLS interception: MONGODB_TLS_CA_FILE, SSL_CERT_FILE, or
MONGODB_TLS_ALLOW_INVALID (insecure, last resort).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError


def _load_dotenv() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(repo_root / ".env")


def atlas_uri_from_env() -> str | None:
    return (
        os.environ.get("MONGODB_URI")
        or os.environ.get("MONGODB_ATLAS_URI")
        or os.environ.get("ATLAS_CONNECTION_STRING")
    )


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _expand_env_path(raw: str) -> Path:
    s = raw.strip().strip('"').strip("'").strip("`")
    return Path(os.path.expandvars(s)).expanduser()


def mongo_client_kwargs_from_env() -> dict:
    kwargs: dict = {}

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
        else:
            print(
                f"warning: TLS CA bundle path invalid or unreadable — {ca_path}",
                file=sys.stderr,
            )

    return kwargs


def main() -> int:
    _load_dotenv()
    uri = atlas_uri_from_env()
    if not uri:
        print(
            "Set one of: MONGODB_URI, MONGODB_ATLAS_URI, or ATLAS_CONNECTION_STRING.\n"
            "Use repo-root .env (gitignored), export in the shell, or use your host’s secrets.\n"
            "Atlas URI guide: https://www.mongodb.com/docs/guides/atlas/connection-string/",
            file=sys.stderr,
        )
        return 1

    client: MongoClient | None = None
    try:
        tls_kwargs = mongo_client_kwargs_from_env()
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=15_000,
            appName="agentevolution-atlas-ping",
            **tls_kwargs,
        )
        client.admin.command("ping")
        version = client.server_info().get("version")

        print("Ping succeeded — Atlas/cluster is reachable from this machine.")
        if version:
            print(f"Server version: {version}")

        try:
            db_names = sorted(client.list_database_names())
        except PyMongoError:
            print(
                "(Could not list databases — user may lack listDatabases privilege; ping is enough.)"
            )
        else:
            preview = db_names[:15]
            more = len(db_names) - len(preview)
            suffix = f" (+{more} more)" if more > 0 else ""
            print(f"Databases ({len(db_names)}): {preview}{suffix}")

        return 0
    except PyMongoError as e:
        print(f"MongoDB connection failed: {e}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
