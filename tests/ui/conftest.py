import pytest
from playwright.sync_api import Page, expect

from tests.ui.pages.dashboard_page import DashboardPage
from tests.ui.pages.login_page import LoginPage

expect.set_options(timeout=5_000)


@pytest.fixture
def login_page(page: Page) -> LoginPage:
    return LoginPage(page).open()


@pytest.fixture
def sign_in(login_page: LoginPage):
    """Call *after* seeding data through the API so the dashboard loads it."""

    def _sign_in(username: str = "tester", password: str = "Passw0rd!") -> DashboardPage:
        login_page.login(username, password)
        dash = DashboardPage(login_page.page)
        expect(dash.current_user).to_have_text(username)
        return dash

    return _sign_in


@pytest.fixture
def dashboard(sign_in) -> DashboardPage:
    """Signed-in dashboard with no pre-seeded data."""
    return sign_in()
