"""Authentication & access control (rule R7, R8)."""
import pytest
from jsonschema import validate

from tests.helpers import schemas

pytestmark = [pytest.mark.api, pytest.mark.security]

PROTECTED_ENDPOINTS = [
    ("GET", "/members"),
    ("GET", "/members/M00001"),
    ("POST", "/members"),
    ("POST", "/contributions"),
    ("GET", "/members/M00001/balance"),
    ("POST", "/members/M00001/withdrawals"),
    ("GET", "/audit-log"),
    ("POST", "/risk/score"),
]


@pytest.mark.smoke
def test_login_with_valid_credentials_returns_bearer_token(anon):
    resp = anon.login()

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) >= 20
    assert body["username"] == "tester"


@pytest.mark.parametrize(
    "username, password",
    [("tester", "wrong"), ("tester", "passw0rd!"), ("nobody", "Passw0rd!"), ("TESTER", "Passw0rd!")],
    ids=["wrong-password", "password-case-sensitive", "unknown-user", "username-case-sensitive"],
)
def test_login_with_invalid_credentials_is_rejected(anon, username, password):
    resp = anon.login(username, password)

    assert resp.status_code == 401
    validate(resp.json(), schemas.ERROR)
    assert "access_token" not in resp.text


@pytest.mark.parametrize("payload", [{}, {"username": "tester"}, {"username": "", "password": "x"}])
def test_login_with_malformed_body_returns_422(anon, payload):
    assert anon.post("/auth/login", json=payload).status_code == 422


@pytest.mark.parametrize("method, path", PROTECTED_ENDPOINTS, ids=[f"{m} {p}" for m, p in PROTECTED_ENDPOINTS])
def test_protected_endpoint_requires_token(anon, method, path):
    resp = anon.request(method, path, json={})

    assert resp.status_code == 401


def test_forged_token_is_rejected(anon):
    anon.session.headers["Authorization"] = "Bearer forged-token-123"

    assert anon.get("/members").status_code == 401


def test_logout_invalidates_token(api):
    token_header = api.session.headers["Authorization"]
    assert api.logout().status_code == 204

    stale = api.without_auth()
    stale.session.headers["Authorization"] = token_header
    assert stale.get("/members").status_code == 401


def test_account_locks_after_five_failed_attempts(anon):
    for _ in range(5):
        assert anon.login("tester", "wrong").status_code == 401

    # Even the correct password must now be refused.
    resp = anon.login("tester", "Passw0rd!")
    assert resp.status_code == 423
    assert "locked" in resp.json()["detail"].lower()


def test_successful_login_resets_failed_attempt_counter(anon):
    for _ in range(4):
        anon.login("tester", "wrong")
    assert anon.login().status_code == 200

    for _ in range(4):
        anon.login("tester", "wrong")
    assert anon.login().status_code == 200, "counter should have been reset by the earlier success"


def test_lockout_is_per_user(anon):
    for _ in range(5):
        anon.login("tester", "wrong")

    assert anon.login("auditor", "Audit#2026").status_code == 200


def test_failed_and_successful_logins_are_audited(anon):
    anon.login("tester", "wrong")
    anon.login()

    log = anon.get("/audit-log").json()
    for entry in log:
        validate(entry, schemas.AUDIT_ENTRY)
    events = [(e["event"], e["actor"]) for e in log]
    assert ("LOGIN_FAILED", "tester") in events
    assert ("LOGIN_SUCCESS", "tester") in events
    assert events.index(("LOGIN_FAILED", "tester")) < events.index(("LOGIN_SUCCESS", "tester"))


def test_password_is_never_written_to_audit_log(anon):
    anon.login("tester", "S3cret-Typo!")
    anon.login()

    assert "S3cret-Typo!" not in anon.get("/audit-log").text
