Fernslop: shared garden plans. FastAPI backend in `backend/`, React frontend in `frontend/`. See `README.md`.

Commands

The backend uses uv for dependencies. Run these from `backend/`:

- `uv sync` - install dependencies
- `uv run pytest` - the whole backend suite
- `uv run pytest app/test_posts.py` - one test file
- `uv run python <PYTHON-FILE>` - run a script

From the repo root, `make test-all` runs the backend, frontend and end-to-end tests.

Documents

- `_docs/process.md` - how work is organized: roles, sizing and the issue lifecycle
- `_docs/team/` - one brief per role (TM, PM, engineer, QA)
- `docs/` - product, getting started, architecture, deployment and observability guides

Rules

- Dependencies go in `pyproject.toml`. Ask before adding one, so other agents
  can pick up the tasks and know what is used
- Commit regularly

