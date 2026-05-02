SHELL := /bin/bash
.PHONY: bootstrap seed api livekit web demo test lint

bootstrap:
	uv sync --all-extras
	cd frontend && (pnpm install || npm install)

seed:
	uv run python -m backend.seeds.run_all

api:
	uv run uvicorn dronan.api.main:app --host 0.0.0.0 --port $${API_PORT:-8000} --reload

livekit:
	uv run python -m dronan.voice.livekit_worker dev

web:
	cd frontend && (pnpm dev || npm run dev)

demo: bootstrap seed
	@bash scripts/demo.sh

test:
	uv run pytest -q
	cd frontend && (pnpm typecheck || npm run typecheck) && (pnpm playwright test || npx playwright test)

lint:
	uv run ruff check backend
	cd frontend && (pnpm lint || npm run lint)
