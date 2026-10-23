for backend, use uv for dependency management. a few useful commands:

uv sync
uv add <PACKAGE-NAME>
uv run python <PYTHON-FILE>

Commands

- `uv sync` - install dependencies
- `uv run pytest` - the whole suite
- `uv run pytest app/test_posts.py` - one test file (from `backend/`)

regularly commit code to git 

Documents

- `_docs/process.md` - how work is organized
- Before writing tests, read `_docs/testing-guidelines.md`
- For anything touching the UI, read `_docs/design-system.md`


Rules

- Dependencies are added in `pyproject.toml`. Do not add one without
  asking so that other agents can pick up the tasks and know best practices etc.
