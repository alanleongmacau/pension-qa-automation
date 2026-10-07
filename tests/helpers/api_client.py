"""Thin wrapper around requests.Session so tests read like business steps."""
from __future__ import annotations

import requests

DEFAULT_USER = ("tester", "Passw0rd!")


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    # -- low level ---------------------------------------------------------
    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        return self.session.request(method, f"{self.base_url}{path}", **kwargs)

    def get(self, path: str, **kw) -> requests.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> requests.Response:
        return self.request("POST", path, **kw)

    # -- auth --------------------------------------------------------------
    def login(self, username: str = DEFAULT_USER[0], password: str = DEFAULT_USER[1]) -> requests.Response:
        resp = self.post("/auth/login", json={"username": username, "password": password})
        if resp.status_code == 200:
            self.session.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
        return resp

    def logout(self) -> requests.Response:
        resp = self.post("/auth/logout")
        self.session.headers.pop("Authorization", None)
        return resp

    def without_auth(self) -> "ApiClient":
        """Return a fresh, unauthenticated client against the same server."""
        return ApiClient(self.base_url, self.timeout)

    # -- business helpers --------------------------------------------------
    def create_member(self, **payload) -> requests.Response:
        return self.post("/members", json=payload)

    def contribute(self, member_id: str, period: str, contributor: str, amount) -> requests.Response:
        return self.post(
            "/contributions",
            json={"member_id": member_id, "period": period, "contributor": contributor, "amount": amount},
        )

    def balance(self, member_id: str) -> requests.Response:
        return self.get(f"/members/{member_id}/balance")

    def withdraw(self, member_id: str, amount) -> requests.Response:
        return self.post(f"/members/{member_id}/withdrawals", json={"amount": amount})

    def risk_score(self, **features) -> requests.Response:
        return self.post("/risk/score", json=features)

    def reset(self) -> None:
        resp = self.post("/test/reset")
        assert resp.status_code == 204, f"State reset failed: {resp.status_code} {resp.text}"
