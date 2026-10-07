"""Load test for the Provident Fund API.

Simulates back-office staff: each virtual user signs in, registers one member,
then mixes read-heavy enquiries with occasional writes and risk-score checks.

Headless run with an SLA gate (non-zero exit code if the SLA is breached):

    locust -f perf/locustfile.py --host http://127.0.0.1:8000 \
           --headless -u 30 -r 10 -t 30s --html reports/perf.html

SLA thresholds can be overridden: SLA_P95_MS=150 SLA_MAX_FAILURE_RATIO=0.005 locust ...
"""
from __future__ import annotations

import itertools
import os
import random
from datetime import date

from locust import HttpUser, between, events, task

SLA_P95_MS = float(os.environ.get("SLA_P95_MS", 200))
SLA_MAX_FAILURE_RATIO = float(os.environ.get("SLA_MAX_FAILURE_RATIO", 0.01))

_ids = itertools.count(1)


def _period(months_back: int) -> str:
    today = date.today()
    idx = today.year * 12 + today.month - 1 - months_back
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


class BackOfficeUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        token = self.client.post("/auth/login", json={"username": "tester", "password": "Passw0rd!"}).json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"

        n = next(_ids) + random.randint(0, 99) * 10_000
        body = {
            "full_name": f"Load User {n}",
            "id_number": f"7{n:06d}({n % 10})",
            "date_of_birth": "1980-01-01",
            "email": f"load{n}@example.com",
        }
        with self.client.post("/members", json=body, catch_response=True, name="/members [create]") as resp:
            if resp.status_code == 409:  # ID collision between runs — not a server fault
                resp.success()
                self.member_id = self.client.get("/members").json()[0]["member_id"]
            else:
                self.member_id = resp.json()["member_id"]
        self.months_back = 0

    @task(5)
    def check_balance(self) -> None:
        self.client.get(f"/members/{self.member_id}/balance", name="/members/[id]/balance")

    @task(3)
    def contribution_history(self) -> None:
        self.client.get(f"/members/{self.member_id}/contributions", name="/members/[id]/contributions")

    @task(2)
    def record_contribution(self) -> None:
        self.months_back += 1
        self.client.post(
            "/contributions",
            json={
                "member_id": self.member_id,
                "period": _period(self.months_back),
                "contributor": random.choice(["employee", "employer"]),
                "amount": round(random.uniform(500, 5_000), 2),
            },
            name="/contributions",
        )

    @task(4)
    def risk_score(self) -> None:
        self.client.post(
            "/risk/score",
            json={
                "amount": round(random.uniform(100, 120_000), 2),
                "is_cross_border": random.random() < 0.25,
                "txn_count_24h": random.randint(0, 25),
                "account_age_days": random.randint(0, 3_650),
            },
            name="/risk/score",
        )


@events.quitting.add_listener
def enforce_sla(environment, **_kw) -> None:
    stats = environment.stats.total
    p95 = stats.get_response_time_percentile(0.95)
    print(f"\nSLA check: requests={stats.num_requests} failure_ratio={stats.fail_ratio:.2%} p95={p95}ms")
    if stats.fail_ratio > SLA_MAX_FAILURE_RATIO:
        print(f"SLA FAILED: failure ratio above {SLA_MAX_FAILURE_RATIO:.0%}")
        environment.process_exit_code = 1
    elif p95 > SLA_P95_MS:
        print(f"SLA FAILED: p95 {p95}ms above {SLA_P95_MS}ms")
        environment.process_exit_code = 1
    else:
        print("SLA PASSED")
        environment.process_exit_code = 0
