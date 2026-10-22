PORT ?= 8091

.PHONY: backend backend-dev test install

install:
	cd backend && uv sync

# Run the backend on $(PORT) (default 8091)
backend:
	cd backend && uv run uvicorn app.main:app --port $(PORT)

# Same, with auto-reload on code changes
backend-dev:
	cd backend && uv run uvicorn app.main:app --port $(PORT) --reload

test:
	cd backend && uv run pytest
