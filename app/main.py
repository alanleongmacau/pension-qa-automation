"""Provident Fund Demo API — the *system under test* for this portfolio.

A deliberately small but realistic back-office service:
member registration, monthly contributions, balance enquiry, withdrawals,
login with lockout, an audit trail, and an ML-based transaction risk score.

Business rules (the test suite is written against these):
  R1  Members must be at least 18 years old on the registration date.
  R2  ID number must follow the Macao resident ID format, e.g. 1234567(8).
  R3  A contribution amount must be > 0, <= 100,000.00 MOP, max 2 decimal places.
  R4  Only one contribution per member / period / contributor type (else 409).
  R5  A contribution period cannot be in the future.
  R6  Withdrawals require the member to be 65 or older (else 403)
      and cannot exceed the available balance (else 422).
  R7  5 consecutive failed logins lock the account (423).
  R8  Every security-relevant or financial event is written to the audit log.

KNOWN DEFECT (intentional, for demonstration): BUG-001 — rule R3's
"max 2 decimal places" is not enforced. See docs/BUG-001.md.

Run:  uvicorn app.main:app --reload     (UI at http://127.0.0.1:8000/)
"""
from __future__ import annotations

import os
import secrets
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.risk_model import MODEL_VERSION, RiskModel

STATIC_DIR = Path(__file__).parent / "static"
MAX_FAILED_LOGINS = 5
MAX_CONTRIBUTION = 100_000

USERS = {"tester": "Passw0rd!", "auditor": "Audit#2026"}

app = FastAPI(
    title="Provident Fund Demo API",
    version="1.0.0",
    description="System under test for an automated testing portfolio.",
)

_lock = threading.Lock()
_risk_model = RiskModel()


# --------------------------------------------------------------------------- state
class _Store:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.tokens: dict[str, str] = {}
        self.failed_logins: dict[str, int] = {}
        self.members: dict[str, dict] = {}
        self.contributions: list[dict] = []
        self.withdrawals: list[dict] = []
        self.audit: list[dict] = []
        self._seq = 0

    def next_member_id(self) -> str:
        self._seq += 1
        return f"M{self._seq:05d}"

    def log(self, event: str, actor: str | None, detail: str = "") -> None:
        self.audit.append(
            {
                "seq": len(self.audit) + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "actor": actor,
                "detail": detail,
            }
        )


store = _Store()


# --------------------------------------------------------------------------- helpers
def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    user = store.tokens.get(authorization.removeprefix("Bearer ").strip())
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


def get_member_or_404(member_id: str) -> dict:
    member = store.members.get(member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Member {member_id} not found")
    return member


def balance_of(member_id: str) -> dict:
    emp = sum(c["amount"] for c in store.contributions if c["member_id"] == member_id and c["contributor"] == "employee")
    er = sum(c["amount"] for c in store.contributions if c["member_id"] == member_id and c["contributor"] == "employer")
    wd = sum(w["amount"] for w in store.withdrawals if w["member_id"] == member_id)
    return {
        "member_id": member_id,
        "employee_total": round(emp, 2),
        "employer_total": round(er, 2),
        "withdrawn_total": round(wd, 2),
        "balance": round(emp + er - wd, 2),
        "currency": "MOP",
    }


# --------------------------------------------------------------------------- schemas
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


class MemberCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    id_number: str = Field(pattern=r"^[1578]\d{6}\(\d\)$", examples=["1234567(8)"])
    date_of_birth: date
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("full_name must not be blank")
        return v.strip()


class ContributionCreate(BaseModel):
    member_id: str
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-09"])
    contributor: Literal["employee", "employer"]
    # BUG-001: rule R3 says max 2 decimal places, but no decimal check is applied here.
    amount: float = Field(gt=0, le=MAX_CONTRIBUTION)


class WithdrawalCreate(BaseModel):
    amount: float = Field(gt=0)


class RiskRequest(BaseModel):
    amount: float = Field(ge=0)
    is_cross_border: bool
    txn_count_24h: int = Field(ge=0)
    account_age_days: int = Field(ge=0)


# --------------------------------------------------------------------------- routes
@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_version": MODEL_VERSION}


@app.post("/auth/login")
def login(body: LoginRequest) -> dict:
    with _lock:
        if store.failed_logins.get(body.username, 0) >= MAX_FAILED_LOGINS:
            store.log("LOGIN_BLOCKED", body.username, "account locked")
            raise HTTPException(status.HTTP_423_LOCKED, "Account locked after repeated failed logins")
        if USERS.get(body.username) != body.password:
            store.failed_logins[body.username] = store.failed_logins.get(body.username, 0) + 1
            store.log("LOGIN_FAILED", body.username, f"attempt {store.failed_logins[body.username]}")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
        store.failed_logins[body.username] = 0
        token = secrets.token_urlsafe(24)
        store.tokens[token] = body.username
        store.log("LOGIN_SUCCESS", body.username)
    return {"access_token": token, "token_type": "bearer", "username": body.username}


@app.post("/auth/logout", status_code=204)
def logout(authorization: str = Header(), user: str = Depends(current_user)) -> None:
    with _lock:
        store.tokens.pop(authorization.removeprefix("Bearer ").strip(), None)
        store.log("LOGOUT", user)


@app.post("/members", status_code=201)
def create_member(body: MemberCreate, user: str = Depends(current_user)) -> dict:
    today = date.today()
    if body.date_of_birth > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "date_of_birth cannot be in the future")
    if age_on(body.date_of_birth, today) < 18:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Member must be at least 18 years old")
    with _lock:
        if any(m["id_number"] == body.id_number for m in store.members.values()):
            raise HTTPException(status.HTTP_409_CONFLICT, "A member with this ID number already exists")
        member = {
            "member_id": store.next_member_id(),
            **body.model_dump(mode="json"),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        store.members[member["member_id"]] = member
        store.log("MEMBER_CREATED", user, member["member_id"])
    return member


@app.get("/members")
def list_members(user: str = Depends(current_user)) -> list[dict]:
    return list(store.members.values())


@app.get("/members/{member_id}")
def get_member(member_id: str, user: str = Depends(current_user)) -> dict:
    return get_member_or_404(member_id)


@app.post("/contributions", status_code=201)
def create_contribution(body: ContributionCreate, user: str = Depends(current_user)) -> dict:
    get_member_or_404(body.member_id)
    today = date.today()
    if body.period > f"{today.year:04d}-{today.month:02d}":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Contribution period cannot be in the future")
    with _lock:
        dup = any(
            c["member_id"] == body.member_id and c["period"] == body.period and c["contributor"] == body.contributor
            for c in store.contributions
        )
        if dup:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{body.contributor} contribution for {body.period} already recorded",
            )
        record = {
            "contribution_id": f"C{len(store.contributions) + 1:06d}",
            **body.model_dump(),
            "recorded_by": user,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        store.contributions.append(record)
        store.log("CONTRIBUTION_CREATED", user, f"{record['contribution_id']} {body.member_id} {body.amount}")
    return record


@app.get("/members/{member_id}/contributions")
def list_contributions(member_id: str, user: str = Depends(current_user)) -> list[dict]:
    get_member_or_404(member_id)
    return sorted(
        (c for c in store.contributions if c["member_id"] == member_id),
        key=lambda c: (c["period"], c["contributor"]),
    )


@app.get("/members/{member_id}/balance")
def get_balance(member_id: str, user: str = Depends(current_user)) -> dict:
    get_member_or_404(member_id)
    return balance_of(member_id)


@app.post("/members/{member_id}/withdrawals", status_code=201)
def withdraw(member_id: str, body: WithdrawalCreate, user: str = Depends(current_user)) -> dict:
    member = get_member_or_404(member_id)
    if age_on(date.fromisoformat(member["date_of_birth"]), date.today()) < 65:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Member is not yet eligible to withdraw (age 65)")
    with _lock:
        if body.amount > balance_of(member_id)["balance"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Insufficient balance")
        record = {
            "withdrawal_id": f"W{len(store.withdrawals) + 1:06d}",
            "member_id": member_id,
            "amount": body.amount,
            "processed_by": user,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        store.withdrawals.append(record)
        store.log("WITHDRAWAL_CREATED", user, f"{record['withdrawal_id']} {member_id} {body.amount}")
    return record


@app.get("/audit-log")
def audit_log(user: str = Depends(current_user)) -> list[dict]:
    return store.audit


@app.post("/risk/score")
def risk_score(body: RiskRequest, user: str = Depends(current_user)) -> dict:
    score = _risk_model.score(body.amount, body.is_cross_border, body.txn_count_24h, body.account_age_days)
    return {"score": round(score, 4), "flagged": score >= 0.5, "model_version": MODEL_VERSION}


@app.post("/test/reset", include_in_schema=False, status_code=204)
def reset_state() -> None:
    """Test hook: wipe all in-memory data. Only available when APP_ENV=test."""
    if os.environ.get("APP_ENV") != "test":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    with _lock:
        store.reset()
