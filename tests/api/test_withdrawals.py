"""Withdrawals (rule R6) and an end-to-end member lifecycle."""
import pytest

from tests.helpers.data_factory import period_offset, years_ago

pytestmark = pytest.mark.api


@pytest.fixture
def retiree_with_balance(api, member_factory):
    """A 70-year-old member with MOP 10,000 in the account."""
    m = member_factory(date_of_birth=years_ago(70).isoformat())
    api.contribute(m["member_id"], period_offset(-1), "employee", 4000)
    api.contribute(m["member_id"], period_offset(-1), "employer", 6000)
    return m


@pytest.mark.parametrize(
    "dob, expected",
    [
        pytest.param(years_ago(65), 201, id="exactly-65"),
        pytest.param(years_ago(65, extra_days=1), 403, id="65-tomorrow"),
        pytest.param(years_ago(40), 403, id="age-40"),
    ],
)
def test_withdrawal_age_eligibility(api, member_factory, dob, expected):
    m = member_factory(date_of_birth=dob.isoformat())
    api.contribute(m["member_id"], period_offset(-1), "employee", 1000)

    assert api.withdraw(m["member_id"], 100).status_code == expected


def test_withdraw_full_balance_leaves_zero(api, retiree_with_balance):
    mid = retiree_with_balance["member_id"]

    assert api.withdraw(mid, 10_000).status_code == 201

    bal = api.balance(mid).json()
    assert bal["withdrawn_total"] == 10_000
    assert bal["balance"] == 0


def test_withdraw_more_than_balance_is_rejected(api, retiree_with_balance):
    mid = retiree_with_balance["member_id"]

    resp = api.withdraw(mid, 10_000.01)

    assert resp.status_code == 422
    assert "insufficient" in resp.json()["detail"].lower()
    assert api.balance(mid).json()["balance"] == 10_000


def test_successive_withdrawals_cannot_overdraw(api, retiree_with_balance):
    mid = retiree_with_balance["member_id"]

    assert api.withdraw(mid, 6_000).status_code == 201
    assert api.withdraw(mid, 4_000.01).status_code == 422
    assert api.withdraw(mid, 4_000).status_code == 201
    assert api.balance(mid).json()["balance"] == 0


@pytest.mark.parametrize("amount", [0, -50, "all"])
def test_invalid_withdrawal_amount_is_rejected(api, retiree_with_balance, amount):
    assert api.withdraw(retiree_with_balance["member_id"], amount).status_code == 422


def test_withdrawal_for_unknown_member_returns_404(api):
    assert api.withdraw("M99999", 10).status_code == 404


@pytest.mark.smoke
def test_member_lifecycle_end_to_end(api, member_factory):
    """Register → contribute for 12 months → check balance → withdraw → audit trail complete."""
    m = member_factory(full_name="Leong Retiree", date_of_birth=years_ago(66).isoformat())
    mid = m["member_id"]

    for offset in range(-12, 0):
        assert api.contribute(mid, period_offset(offset), "employee", 500).status_code == 201
        assert api.contribute(mid, period_offset(offset), "employer", 500).status_code == 201
    assert api.balance(mid).json()["balance"] == 12_000

    w = api.withdraw(mid, 2_000).json()
    assert api.balance(mid).json()["balance"] == 10_000

    events = [e["event"] for e in api.get("/audit-log").json()]
    assert events.count("MEMBER_CREATED") == 1
    assert events.count("CONTRIBUTION_CREATED") == 24
    assert events.count("WITHDRAWAL_CREATED") == 1
    assert any(w["withdrawal_id"] in e["detail"] for e in api.get("/audit-log").json())
