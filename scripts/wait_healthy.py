"""Poll API + frontend until both are healthy, then exit."""

from __future__ import annotations

import os
import time

import httpx

API_BASE = os.environ.get("NEXT_PUBLIC_API_BASE", "http://localhost:8000")
WEB_PORT = os.environ.get("WEB_PORT", "3000")
WEB_BASE = f"http://localhost:{WEB_PORT}"


def wait(url: str, timeout: float = 60.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                print(f"OK {url} [{r.status_code}] in {time.time()-start:.1f}s")
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit(f"Timed out waiting for {url}")


if __name__ == "__main__":
    wait(f"{API_BASE}/health")
    wait(f"{WEB_BASE}/")
