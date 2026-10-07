"""UI flows. Test data is seeded through the API (fast, reliable) and the
browser is used only for the behaviour under test — a common hybrid pattern."""
import re

import pytest
from playwright.sync_api import expect

from tests.helpers.data_factory import macao_id, member_payload, period_offset, years_ago

pytestmark = pytest.mark.ui

LAST_MONTH = period_offset(-1)


# ---------------------------------------------------------------- member registration
@pytest.mark.smoke
def test_register_member_through_ui(dashboard):
    dashboard.register_member("Chan Tai Man", macao_id(4321), years_ago(30).isoformat(), "chan@example.com")

    expect(dashboard.member_message).to_have_text(re.compile(r"Member M\d{5} registered"))
    expect(dashboard.contrib_member).to_contain_text("Chan Tai Man")


def test_invalid_id_number_shows_validation_error(dashboard):
    dashboard.register_member("Bad ID", "12345", years_ago(30).isoformat(), "bad@example.com")

    expect(dashboard.member_message).to_have_class("msg err")
    expect(dashboard.member_message).to_contain_text("id_number")


def test_under_age_member_is_rejected_in_ui(dashboard):
    dashboard.register_member("Young Person", macao_id(4322), years_ago(17).isoformat(), "young@example.com")

    expect(dashboard.member_message).to_have_text("Member must be at least 18 years old")


@pytest.mark.security
def test_member_name_is_rendered_as_text_not_html(api, sign_in):
    """Stored values must be escaped, so a malicious name cannot run script (XSS)."""
    api.create_member(**member_payload(full_name='<img src=x onerror="window.__xss=1">Evil'))

    dash = sign_in()

    expect(dash.contrib_member).to_contain_text("<img src=x")
    assert dash.page.evaluate("window.__xss") is None


# ---------------------------------------------------------------- contributions
@pytest.mark.smoke
def test_recording_contribution_updates_summary(member_factory, sign_in):
    member = member_factory()
    dash = sign_in()

    dash.record_contribution(LAST_MONTH, "employee", "1500", member_id=member["member_id"])
    expect(dash.contrib_message).to_contain_text("recorded")
    dash.record_contribution(LAST_MONTH, "employer", "2250.50")

    expect(dash.employee_total).to_have_text("1,500.00")
    expect(dash.employer_total).to_have_text("2,250.50")
    expect(dash.balance).to_have_text("3,750.50")
    expect(dash.contrib_rows).to_have_count(2)


def test_ui_balance_matches_api_balance(api, member_factory, sign_in):
    """Cross-layer consistency: what the user sees equals what the back end holds."""
    member = member_factory()
    for offset in range(-6, 0):
        api.contribute(member["member_id"], period_offset(offset), "employee", 1234.56)
    api_balance = api.balance(member["member_id"]).json()["balance"]

    dash = sign_in()
    dash.select_member(member["member_id"])

    expect(dash.balance).to_have_text(f"{api_balance:,.2f}")
    expect(dash.contrib_rows).to_have_count(6)


def test_duplicate_contribution_shows_conflict_message(api, member_factory, sign_in):
    member = member_factory()
    api.contribute(member["member_id"], LAST_MONTH, "employee", 1000)

    dash = sign_in()
    dash.record_contribution(LAST_MONTH, "employee", "1000", member_id=member["member_id"])

    expect(dash.contrib_message).to_have_text(f"employee contribution for {LAST_MONTH} already recorded")
    expect(dash.balance).to_have_text("1,000.00")


@pytest.mark.parametrize(
    "amount, fragment",
    [("0", "greater than 0"), ("100000.01", "less than or equal to 100000")],
    ids=["zero", "above-max"],
)
def test_out_of_range_amount_shows_validation_message(member_factory, sign_in, amount, fragment):
    member = member_factory()
    dash = sign_in()

    dash.record_contribution(LAST_MONTH, "employee", amount, member_id=member["member_id"])

    expect(dash.contrib_message).to_contain_text(fragment)
    expect(dash.balance).to_have_text("0.00")
