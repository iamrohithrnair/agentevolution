"""MongoDB Atlas Trigger source.

These ``.js`` files are deployed to Atlas via the ``atlas`` CLI in P8.
Each trigger's body POSTs to a `/internal/...` endpoint on the FastAPI
backend running on Cloud Run.
"""
