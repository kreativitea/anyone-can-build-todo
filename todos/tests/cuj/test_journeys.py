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
from todos.tests.integration.helpers import page_forms, page_without_csrf

EMPTY = "<li>Nothing to do yet. Add something above.</li>"


def todo_row(todo, due="", done=False):
    """One to-do on the list, exactly as the page must show it.

    `due` is the due-date text, like "due 5 Oct 2026", or "" for none.
    """
    due_html = f'<small class="due">{due}</small>' if due else ""
    return (
        f'<li class="{"done" if done else ""}">'
        f'<span class="title">{escape(todo.title)}{due_html}</span>'
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

        page = self.press(page, "Add", title="Buy milk", due_date="2026-10-05")
        milk = Todo.objects.get()
        due = "due 5 Oct 2026"
        self.assert_list(page, todo_row(milk, due))

        page = self.press(page, "Done")
        self.assert_list(page, todo_row(milk, due, done=True))

        page = self.press(page, "Undo")
        self.assert_list(page, todo_row(milk, due))

        page = self.press(page, "Delete")
        self.assert_list(page, EMPTY)
