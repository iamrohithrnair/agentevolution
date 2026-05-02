"""Seed scripts for Dronan. Each module exports an async ``main(db)`` and a
CLI entrypoint runnable as ``python -m backend.seeds.<name>``.

All seeds are **idempotent**: running them twice yields zero changes
(``upserted_count == 0``, ``modified_count == 0``).
"""
