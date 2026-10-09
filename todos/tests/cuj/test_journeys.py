import os
import re

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright


class JourneyTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        # Playwright runs an event loop, and Django refuses database work while
        # one is running. That is a safety check for real async code; this test
        # has none, so turning it off here is safe.
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def test_plan_and_finish_a_todo(self):
        page = self.browser.new_page()
        # Wait at most 5 seconds for each step, so a broken page fails fast.
        page.set_default_timeout(5_000)
        page.goto(self.live_server_url)
        expect(page.get_by_text("Nothing to do yet")).to_be_visible()

        page.get_by_label("New to-do").fill("Buy milk")
        page.get_by_label("Due date").fill("2026-10-05")
        page.get_by_role("button", name="Add").click()
        item = page.get_by_role("listitem").filter(has_text="Buy milk")
        expect(item).to_be_visible()
        expect(item).to_contain_text("due 5 Oct 2026")

        item.get_by_role("button", name="Done").click()
        expect(item).to_have_class(re.compile(r"\bdone\b"))

        item.get_by_role("button", name="Undo").click()
        expect(item).not_to_have_class(re.compile(r"\bdone\b"))

        item.get_by_role("button", name="Delete").click()
        expect(page.get_by_text("Nothing to do yet")).to_be_visible()
