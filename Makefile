SHELL := /bin/bash
.PHONY: bootstrap seed api livekit web demo test lint

bootstrap:
	uv sync --all-extras
	cd frontend && (pnpm install || npm install)

seed:
	uv run python -m seeds.create_indexes
	uv run python -m seeds.seed_facilities
	uv run python -m seeds.seed_no_fly_zones
	uv run python -m seeds.seed_regulations
	uv run python -m seeds.seed_synthetic_emergencies
	uv run python -m seeds.seed_drones
	uv run python -m seeds.seed_demo_memory
	uv run python -m seeds.seed_agent_skills

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
