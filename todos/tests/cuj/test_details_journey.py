"""The journey "plan and finish a to-do", with the details pane, in Django's test client.

The owner decided: no real-browser tests. So each step is what the browser
sends (a GET of a link, a POST of a form) and what the page shows after it.
"""

import re
from html import unescape

from django.test import TestCase
from django.utils import timezone

from todos.models import Todo
from todos.tests.integration.helpers import (
    log_in,
    make_user,
    page_parts,
    pane_element,
    show_date,
)


def link_named(page, name):
    """The address of the one link whose whole text is `name` (exact, like a click)."""
    found = re.findall(r'<a href="([^"]*)"[^>]*>([^<]*)</a>', page)
    hrefs = [unescape(href) for href, text in found if unescape(text) == name]
    return hrefs[0] if len(hrefs) == 1 else None


class DetailsJourneyTests(TestCase):
    def test_plan_and_finish_a_todo_with_the_details_pane(self):
        make_user("ana")  # ana has an account; she logs in on the real page
        page = log_in(self.client, "ana")
        self.assertContains(
            page, "<li>Nothing to do yet. Add something above.</li>", html=True
        )

        page = self.client.post(
            "/add/", {"title": "Buy milk", "due_date": "2026-10-05"}, follow=True
        )
        self.assertEqual(page_parts(page).titles, ["Buy milk"])
        milk = Todo.objects.get()
        created = show_date(timezone.localtime(milk.created_at).date())

        # Click the title: the details pane opens.
        href = link_named(page.content.decode(), "Buy milk")
        self.assertIsNotNone(href, "the title Buy milk is not a link")
        page = self.client.get(href)
        self.assertEqual(page_parts(page).panes, ["Details"])
        pane = pane_element(
            milk, due="5 Oct 2026", priority="Medium", created=created, close_url="/"
        )
        self.assertContains(page, pane, count=1, html=True)

        # Done: after the POST and the redirect, the pane is still open.
        done_url = f"/{milk.pk}/toggle/?selected={milk.pk}"
        self.assertIn(done_url, page_parts(page).post_actions)
        page = self.client.post(done_url, {"done": "1"}, follow=True)
        pane = pane_element(
            milk,
            status="Completed",
            due="5 Oct 2026",
            priority="Medium",
            created=created,
            close_url="/",
        )
        self.assertContains(page, pane, count=1, html=True)

        # Delete: the to-do is gone, and so is the pane.
        delete_url = f"/{milk.pk}/delete/?selected={milk.pk}"
        self.assertIn(delete_url, page_parts(page).post_actions)
        page = self.client.post(delete_url, follow=True)
        self.assertEqual(page_parts(page).panes, [])
        self.assertContains(
            page, "<li>Nothing to do yet. Add something above.</li>", html=True
        )
