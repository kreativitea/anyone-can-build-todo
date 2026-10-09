"""The critical user journeys: what a person does, from start to finish.

Each journey uses Django's test client, not a real browser. Every step reads
the form from the page (its address and its fields, with the CSRF token), sends
it like a browser would, follows the redirect, and checks the page exactly. So
a journey proves that the page's own forms really work.
"""

from django.test import Client, TestCase
from django.urls import reverse

from todos.models import Todo
from todos.tests.integration.helpers import page_forms, page_without_csrf

EMPTY = "<li>Nothing to do yet. Add something above.</li>"


def todo_row(todo, done=False):
    """One to-do on the list, exactly as the page must show it."""
    return (
        f'<li class="{"done" if done else ""}">'
        f'<span class="title">{todo.title}'
        '<small class="due">due 5 Oct 2026</small></span>'
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

    def press(self, page, button, **typed):
        """Press the one button called `button`, as a browser would.

        The address and the fields come from the form on the page.
        """
        forms = [f for f in page_forms(page) if f.button == button]
        self.assertEqual(len(forms), 1, f"want one {button!r} button on the page")
        form = forms[0]
        self.assertEqual(form.method, "post")
        self.assertIn("csrfmiddlewaretoken", form.fields, f"{button!r} has no token")
        response = self.client.post(form.action, form.data(**typed), follow=True)
        self.assertEqual(response.redirect_chain, [(reverse("todo_list"), 302)])
        return response

    def assert_list(self, page, row):
        self.assertInHTML(row, page_without_csrf(page), count=1)

    def test_plan_and_finish_a_todo(self):
        page = self.client.get(reverse("todo_list"))
        self.assert_list(page, EMPTY)

        page = self.press(page, "Add", title="Buy milk", due_date="2026-10-05")
        milk = Todo.objects.get()
        self.assert_list(page, todo_row(milk))

        page = self.press(page, "Done")
        self.assert_list(page, todo_row(milk, done=True))

        page = self.press(page, "Undo")
        self.assert_list(page, todo_row(milk))

        page = self.press(page, "Delete")
        self.assert_list(page, EMPTY)
