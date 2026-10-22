"""Fixtures for the end-to-end suite.

The suite runs against the real stack from ``docker-compose.yaml`` (Postgres +
the app serving the built frontend). By default it starts its own copy under a
separate compose project name and a free port, so it never touches a stack you
are running by hand, and it removes that copy (and its database volume) after.

Environment variables:
  E2E_BASE_URL    test an already running stack instead of starting one
  E2E_KEEP_STACK  set to 1 to leave the compose stack running afterwards
  E2E_HEADED      set to 1 to watch the browsers
"""

import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yaml"
COMPOSE_PROJECT = "fernslop-e2e"
STARTUP_TIMEOUT_S = 120


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_serving(url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/rooms", timeout=3) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError(f"{url} was not serving /api/rooms after {STARTUP_TIMEOUT_S}s")


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    external = os.environ.get("E2E_BASE_URL")
    if external:
        yield external.rstrip("/")
        return

    port = _free_port()
    env = {**os.environ, "APP_PORT": str(port)}
    compose = ["docker", "compose", "-f", str(COMPOSE_FILE), "-p", COMPOSE_PROJECT]
    try:
        subprocess.run([*compose, "up", "-d", "--build", "--wait"], check=True, env=env)
        url = f"http://localhost:{port}"
        _wait_until_serving(url)
        yield url
    finally:
        if os.environ.get("E2E_KEEP_STACK") != "1":
            subprocess.run([*compose, "down", "--volumes", "--remove-orphans"], env=env, check=False)


@pytest.fixture(scope="session")
def playwright_instance() -> Iterator[Playwright]:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Iterator[Browser]:
    browser = playwright_instance.chromium.launch(headless=os.environ.get("E2E_HEADED") != "1")
    yield browser
    browser.close()


@pytest.fixture
def new_gardener(browser: Browser, base_url: str) -> Iterator[callable]:
    """Factory for a separate browser session.

    Each call is its own browser context, so it has its own localStorage and
    therefore its own anonymous identity (the app has no accounts). The context
    may read and write the clipboard because the Share button copies the link.
    """
    contexts: list[BrowserContext] = []

    def make() -> BrowserContext:
        context = browser.new_context(
            base_url=base_url,
            viewport={"width": 1280, "height": 900},
            permissions=["clipboard-read", "clipboard-write"],
        )
        context.set_default_timeout(10_000)
        contexts.append(context)
        return context

    yield make
    for context in contexts:
        context.close()
