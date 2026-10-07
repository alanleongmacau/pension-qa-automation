"""Shared fixtures.

* Starts the system under test once per session (or targets $SUT_URL if set).
* Resets server state before every test, so tests are independent and can run in any order.
* Provides an authenticated API client and a member factory.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from tests.helpers.api_client import ApiClient
from tests.helpers.data_factory import member_payload

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_healthy(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{url}/health", timeout=1).status_code == 200:
                return
        except requests.RequestException as exc:
            last_err = exc
        time.sleep(0.2)
    raise RuntimeError(f"System under test did not become healthy at {url}: {last_err}")


@pytest.fixture(scope="session")
def base_url() -> str:
    """URL of the system under test. Overrides pytest-playwright's base_url too."""
    external = os.environ.get("SUT_URL")
    if external:
        _wait_until_healthy(external)
        yield external.rstrip("/")
        return

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    log = open(ROOT / "reports" / "server.log", "w") if (ROOT / "reports").is_dir() else subprocess.DEVNULL
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env={**os.environ, "APP_ENV": "test"},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_until_healthy(url)
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(autouse=True)
def _reset_state(base_url: str) -> None:
    ApiClient(base_url).reset()


@pytest.fixture
def anon(base_url: str) -> ApiClient:
    """Unauthenticated client."""
    return ApiClient(base_url)


@pytest.fixture
def api(base_url: str) -> ApiClient:
    """Client logged in as the default back-office user."""
    client = ApiClient(base_url)
    assert client.login().status_code == 200
    return client


@pytest.fixture
def member_factory(api: ApiClient):
    """Create a valid member (overrides allowed) and return its JSON body."""

    def _create(**overrides) -> dict:
        resp = api.create_member(**member_payload(**overrides))
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _create


@pytest.fixture
def member(member_factory) -> dict:
    return member_factory()
