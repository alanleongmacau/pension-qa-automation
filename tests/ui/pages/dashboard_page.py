from playwright.sync_api import Locator, Page


class DashboardPage:
    def __init__(self, page: Page):
        self.page = page
        self.current_user: Locator = page.get_by_test_id("current-user")
        self.logout_button: Locator = page.get_by_test_id("logout-button")

        # register member
        self.member_name = page.get_by_test_id("member-name")
        self.member_id_number = page.get_by_test_id("member-id-number")
        self.member_dob = page.get_by_test_id("member-dob")
        self.member_email = page.get_by_test_id("member-email")
        self.member_submit = page.get_by_test_id("member-submit")
        self.member_message = page.get_by_test_id("member-message")

        # contribution
        self.contrib_member = page.get_by_test_id("contrib-member")
        self.contrib_period = page.get_by_test_id("contrib-period")
        self.contrib_type = page.get_by_test_id("contrib-type")
        self.contrib_amount = page.get_by_test_id("contrib-amount")
        self.contrib_submit = page.get_by_test_id("contrib-submit")
        self.contrib_message = page.get_by_test_id("contrib-message")

        # summary
        self.employee_total = page.get_by_test_id("employee-total")
        self.employer_total = page.get_by_test_id("employer-total")
        self.balance = page.get_by_test_id("balance")
        self.contrib_rows = page.get_by_test_id("contrib-row")

    def register_member(self, full_name: str, id_number: str, dob: str, email: str) -> None:
        self.member_name.fill(full_name)
        self.member_id_number.fill(id_number)
        self.member_dob.fill(dob)
        self.member_email.fill(email)
        self.member_submit.click()

    def select_member(self, member_id: str) -> None:
        self.contrib_member.select_option(member_id)

    def record_contribution(self, period: str, contributor: str, amount: str, member_id: str | None = None) -> None:
        if member_id:
            self.select_member(member_id)
        self.contrib_period.fill(period)
        self.contrib_type.select_option(contributor)
        self.contrib_amount.fill(amount)
        self.contrib_submit.click()

    def logout(self) -> None:
        self.logout_button.click()
