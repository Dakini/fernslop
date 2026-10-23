for backend, use uv for dependency management. a few useful commands:

uv sync
uv add <PACKAGE-NAME>
uv run python <PYTHON-FILE>

Commands

- `uv sync` - install dependencies
- `uv run pytest` - the whole suite
- `uv run pytest app/test_posts.py` - one test file (from `backend/`)

regularly commit code to git 

