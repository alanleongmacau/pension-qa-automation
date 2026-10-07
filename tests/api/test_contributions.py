"""Contributions and balances (rules R3, R4, R5)."""
import json
from pathlib import Path

import pytest
from jsonschema import FormatChecker, validate

from tests.helpers import schemas
from tests.helpers.data_factory import current_period, period_offset

pytestmark = pytest.mark.api

AMOUNT_CASES = json.loads((Path(__file__).parents[1] / "data" / "contribution_amounts.json").read_text())["cases"]
LAST_MONTH = period_offset(-1)


@pytest.mark.smoke
def test_record_contribution_returns_201_and_matches_contract(api, member):
    resp = api.contribute(member["member_id"], LAST_MONTH, "employee", 1500)

    assert resp.status_code == 201
    validate(resp.json(), schemas.CONTRIBUTION, format_checker=FormatChecker())
    assert resp.json()["recorded_by"] == "tester"


# ---------------------------------------------------------------- R3 data-driven boundaries
@pytest.mark.parametrize("case", AMOUNT_CASES, ids=[c["id"] for c in AMOUNT_CASES])
def test_contribution_amount_boundaries(api, member, case):
    resp = api.contribute(member["member_id"], LAST_MONTH, "employee", case["amount"])

    assert resp.status_code == case["expected_status"], resp.text


@pytest.mark.xfail(strict=True, reason="BUG-001: amounts with >2 decimal places are accepted (see docs/BUG-001.md)")
@pytest.mark.parametrize("amount", [100.005, 0.001, 2500.1234])
def test_amount_with_more_than_two_decimals_is_rejected(api, member, amount):
    resp = api.contribute(member["member_id"], LAST_MONTH, "employee", amount)

    assert resp.status_code == 422


# ---------------------------------------------------------------- R4 duplicates
def test_duplicate_contribution_same_period_and_type_returns_409(api, member):
    assert api.contribute(member["member_id"], LAST_MONTH, "employee", 1000).status_code == 201

    resp = api.contribute(member["member_id"], LAST_MONTH, "employee", 999)

    assert resp.status_code == 409
    assert api.balance(member["member_id"]).json()["employee_total"] == 1000, "duplicate must not change balance"


def test_employee_and_employer_may_contribute_for_same_period(api, member):
    assert api.contribute(member["member_id"], LAST_MONTH, "employee", 1000).status_code == 201
    assert api.contribute(member["member_id"], LAST_MONTH, "employer", 1000).status_code == 201


def test_same_period_allowed_for_different_members(api, member_factory):
    a, b = member_factory(), member_factory()

    assert api.contribute(a["member_id"], LAST_MONTH, "employee", 500).status_code == 201
    assert api.contribute(b["member_id"], LAST_MONTH, "employee", 500).status_code == 201


# ---------------------------------------------------------------- R5 periods
@pytest.mark.parametrize(
    "period, expected",
    [
        pytest.param(current_period(), 201, id="current-month"),
        pytest.param(period_offset(-120), 201, id="ten-years-ago"),
        pytest.param(period_offset(1), 422, id="next-month"),
        pytest.param(period_offset(13), 422, id="next-year"),
        pytest.param("2026-13", 422, id="month-13"),
        pytest.param("2026-00", 422, id="month-00"),
        pytest.param("2026-1", 422, id="single-digit-month"),
        pytest.param("26-01", 422, id="two-digit-year"),
        pytest.param("2026/01", 422, id="slash-separator"),
    ],
)
def test_contribution_period_validation(api, member, period, expected):
    assert api.contribute(member["member_id"], period, "employer", 800).status_code == expected


@pytest.mark.parametrize("contributor", ["Employee", "self", "", None])
def test_invalid_contributor_type_is_rejected(api, member, contributor):
    assert api.contribute(member["member_id"], LAST_MONTH, contributor, 100).status_code == 422


def test_contribution_for_unknown_member_returns_404(api):
    assert api.contribute("M99999", LAST_MONTH, "employee", 100).status_code == 404


# ---------------------------------------------------------------- balances
def test_balance_of_new_member_is_zero(api, member):
    resp = api.balance(member["member_id"])

    validate(resp.json(), schemas.BALANCE)
    assert resp.json()["balance"] == 0


def test_balance_sums_contributions_by_contributor_type(api, member):
    mid = member["member_id"]
    for months_back, emp, er in [(3, 1000, 1500), (2, 1000, 1500), (1, 1200.50, 1800.25)]:
        api.contribute(mid, period_offset(-months_back), "employee", emp)
        api.contribute(mid, period_offset(-months_back), "employer", er)

    bal = api.balance(mid).json()

    assert bal["employee_total"] == pytest.approx(3200.50)
    assert bal["employer_total"] == pytest.approx(4800.25)
    assert bal["balance"] == pytest.approx(8000.75)


def test_balances_are_isolated_between_members(api, member_factory):
    a, b = member_factory(), member_factory()
    api.contribute(a["member_id"], LAST_MONTH, "employee", 700)

    assert api.balance(b["member_id"]).json()["balance"] == 0


def test_contribution_history_is_sorted_by_period(api, member):
    mid = member["member_id"]
    for offset in (-1, -3, -2):
        api.contribute(mid, period_offset(offset), "employee", 100)

    periods = [c["period"] for c in api.get(f"/members/{mid}/contributions").json()]

    assert periods == [period_offset(-3), period_offset(-2), period_offset(-1)]


def test_contribution_is_audited(api, member):
    created = api.contribute(member["member_id"], LAST_MONTH, "employee", 1500).json()

    log = api.get("/audit-log").json()

    assert any(e["event"] == "CONTRIBUTION_CREATED" and created["contribution_id"] in e["detail"] for e in log)
