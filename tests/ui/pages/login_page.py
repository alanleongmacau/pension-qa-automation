from playwright.sync_api import Locator, Page


class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.username: Locator = page.get_by_test_id("username")
        self.password: Locator = page.get_by_test_id("password")
        self.submit: Locator = page.get_by_test_id("login-button")
        self.message: Locator = page.get_by_test_id("login-message")

    def open(self) -> "LoginPage":
        self.page.goto("/")
        return self

    def login(self, username: str, password: str) -> None:
        self.username.fill(username)
        self.password.fill(password)
        self.submit.click()
