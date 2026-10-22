import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.static import SHELL_FILE, STATIC_DIR_ENV


@pytest.fixture
def frontend_client(tmp_path, monkeypatch):
    (tmp_path / SHELL_FILE).write_text("<html>shell</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setenv(STATIC_DIR_ENV, str(tmp_path))
    return TestClient(create_app())


def test_files_and_spa_routes_are_served_and_api_stays_json(frontend_client):
    assert frontend_client.get("/assets/app.js").text == "console.log(1)"
    assert frontend_client.get("/r/abc").text == "<html>shell</html>"
    assert frontend_client.get("/api/health").json() == {"status": "ok"}
    missing = frontend_client.get("/api/nope")
    assert missing.status_code == 404
    assert missing.json()["message"]


def test_paths_cannot_escape_the_static_dir(frontend_client):
    response = frontend_client.get("/..%2f..%2fetc/passwd")

    assert response.text == "<html>shell</html>"
