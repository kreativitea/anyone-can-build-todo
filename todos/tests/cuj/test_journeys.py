"""The critical user journeys: what a person does, from start to finish.

Each journey uses Django's test client, not a real browser. Every step reads
the form from the page (its address and its fields, with the CSRF token), sends
it like a browser would, follows the redirect, and checks the page exactly. So
a journey proves that the page's own forms really work.
"""

from django.test import Client, TestCase
from django.urls import reverse
from django.utils.html import escape

from todos.models import Todo
from todos.tests.integration.helpers import (
    link_href,
    page_forms,
    page_without_csrf,
    title_element,
)

EMPTY = "<li>Nothing to do yet. Add something above.</li>"
HIGH_LABEL = '<span class="priority high">High priority</span>'


def todo_row(todo, done=False):
    """One to-do on the list, exactly as the page must show it.

    The title, its priority label and its due date come from `title_element`,
    which builds them from the to-do itself. Then the Edit link, Done and Delete.
    """
    return (
        f'<li id="todo-{todo.pk}" class="{"done" if done else ""}">'
        f"{title_element(todo)}"
        f'<a class="edit" href="{reverse("todo_edit", args=[todo.pk])}" '
        f'aria-label="Edit {escape(todo.title)}">Edit</a>'
        f'<form method="post" action="{reverse("todo_toggle", args=[todo.pk])}">'
        f'<button type="submit">{"Undo" if done else "Done"}</button></form>'
        f'<form method="post" action="{reverse("todo_delete", args=[todo.pk])}">'
        '<button type="submit">Delete</button></form>'
        "</li>"
    )


class JourneyTests(TestCase):
    def setUp(self):
        # Like a real browser: a request without the page's CSRF token fails.
        self.client = Client(enforce_csrf_checks=True)

    def press(self, page, button_text, **typed):
        """Press the one button with exactly this text, as a browser would.

        The address and the fields come from the button's form on the page,
        and the button's own name/value is sent too.
        """
        pairs = [
            (form, button)
            for form in page_forms(page)
            for button in form.buttons
            if button.text == button_text
        ]
        self.assertEqual(len(pairs), 1, f"want one {button_text!r} button")
        form, button = pairs[0]
        self.assertEqual(form.method, "post")
        self.assertIn(
            "csrfmiddlewaretoken", form.fields, f"{button_text!r} has no token"
        )
        response = self.client.post(
            form.action, form.data(button, **typed), follow=True
        )
        self.assertEqual(response.redirect_chain, [(reverse("todo_list"), 302)])
        return response

    def assert_list(self, page, row):
        self.assertInHTML(row, page_without_csrf(page), count=1)

    def test_plan_and_finish_a_todo(self):
        page = self.client.get(reverse("todo_list"))
        self.assert_list(page, EMPTY)

        # The priority is not typed: the form sends the option the page selected.
        # The row has no label, so that option was Medium.
        page = self.press(page, "Add", title="Buy milk", due_date="2026-10-05")
        milk = Todo.objects.get()
        self.assertIn('<small class="due">due 5 Oct 2026</small>', todo_row(milk))
        self.assertNotIn("priority", todo_row(milk))
        self.assert_list(page, todo_row(milk))

        # Fix a typo: open the edit page from the row, change the title, Save.
        page = self.client.get(link_href(page, "Edit Buy milk"))
        self.assertEqual(page.status_code, 200)
        page = self.press(page, "Save", title="Buy oat milk")
        milk.refresh_from_db()
        self.assertEqual(milk.title, "Buy oat milk")
        self.assertEqual(milk.due_date.isoformat(), "2026-10-05")
        self.assert_list(page, todo_row(milk))

        page = self.press(page, "Done")
        self.assert_list(page, todo_row(milk, done=True))

        page = self.press(page, "Undo")
        self.assert_list(page, todo_row(milk))

        page = self.press(page, "Delete")
        self.assert_list(page, EMPTY)

    def test_a_high_priority_todo_keeps_its_label_when_done(self):
        page = self.client.get(reverse("todo_list"))

        page = self.press(page, "Add", title="Pay rent", priority="3")
        rent = Todo.objects.get()
        self.assertIn(HIGH_LABEL, todo_row(rent))
        self.assert_list(page, todo_row(rent))

        page = self.press(page, "Done")
        self.assert_list(page, todo_row(rent, done=True))
