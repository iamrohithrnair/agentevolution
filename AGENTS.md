# Agent instructions

## Stack and layout

- **Frontend:** use **Next.js**. All frontend code, config, and assets belong in **`frontend/`** (app router, components, public assets, `package.json`, etc.). Do not place the Next.js app at the repository root.
- **Backend:** use **Python**. All backend code stays under **`backend/`** (see below).

## Frontend UI/UX quality

Use the **`ui-ux-pro-max`** skill when designing, building, or refining the frontend. Follow that skill’s workflow (design-system generation, domain/stack searches such as **`nextjs`**, accessibility and interaction guidelines) so the UI ships as **polished, production-ready** work—not placeholder styling.

## Python environment and packages

Use **uv** for all Python environment and dependency management in this repository. Do not use `pip install` directly on the system Python, and do not commit ad-hoc virtualenvs outside what uv creates.

- **Virtual environment:** create or refresh with `uv venv` (`.venv` at the repo root).
- **Dependencies:** add or update with `uv add <package>` / `uv remove <package>`; keep the lockfile in sync with `uv lock` when appropriate.
- **Run commands:** prefer `uv run <command>` so execution uses the project environment without manual activation mistakes.

## Backend (Python) code layout

All Python application and library code belongs under **`backend/`**. New modules, scripts, tests, and packages should live there (not at the repository root).
