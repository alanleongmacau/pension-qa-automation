import pytest
from playwright.sync_api import expect

from tests.ui.pages.dashboard_page import DashboardPage

pytestmark = pytest.mark.ui


@pytest.mark.smoke
def test_user_can_sign_in_and_sees_dashboard(login_page):
    login_page.login("tester", "Passw0rd!")

    dash = DashboardPage(login_page.page)
    expect(dash.current_user).to_have_text("tester")
    expect(dash.member_submit).to_be_visible()
    expect(login_page.submit).to_be_hidden()


def test_wrong_password_shows_error_and_stays_on_login(login_page):
    login_page.login("tester", "not-my-password")

    expect(login_page.message).to_have_text("Invalid username or password")
    expect(login_page.message).to_have_class("msg err")
    expect(login_page.submit).to_be_visible()


def test_lockout_message_after_five_failed_attempts(login_page):
    for _ in range(5):
        login_page.login("tester", "wrong")
        expect(login_page.message).to_contain_text("Invalid")

    login_page.login("tester", "Passw0rd!")

    expect(login_page.message).to_contain_text("locked")


def test_password_field_is_masked(login_page):
    expect(login_page.password).to_have_attribute("type", "password")


def test_logout_returns_to_login_and_clears_password(dashboard):
    dashboard.logout()

    login = dashboard.page.get_by_test_id("login-button")
    expect(login).to_be_visible()
    expect(dashboard.page.get_by_test_id("password")).to_have_value("")
    expect(dashboard.current_user).to_be_hidden()
