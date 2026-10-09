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
    page_parts,
    page_without_csrf,
    title_element,
    toggle_form,
)

EMPTY = "<li>Nothing to do yet. Add something above.</li>"
HIGH_LABEL = '<span class="priority high">High priority</span>'


def todo_row(todo, done=False, repeat="", progress=""):
    """One to-do on the list, exactly as the page must show it.

    The title, its priority label and its due date come from `title_element`,
    which builds them from the to-do itself. `repeat` is the words an open
    repeating to-do shows, like "Every week". Then the steps link `progress`
    (if any), the Edit link, Done and Delete.
    """
    return (
        f'<li id="todo-{todo.pk}" class="{"done" if done else ""}">'
        f"{title_element(todo, repeat=repeat)}{progress}"
        f'<a class="edit" href="{reverse("todo_edit", args=[todo.pk])}" '
        f'aria-label="Edit {escape(todo.title)}">Edit</a>'
        f"{toggle_form(todo, done)}"
        f'<form method="post" action="{reverse("todo_delete", args=[todo.pk])}">'
        '<button type="submit">Delete</button></form>'
        "</li>"
    )


class JourneyTests(TestCase):
    def setUp(self):
        # Like a real browser: a request without the page's CSRF token fails.
        self.client = Client(enforce_csrf_checks=True)

    def press(self, page, button_text, lands_on=None, **typed):
        """Press the one button with exactly this name, as a browser would.

        The name is what a screen reader says: the aria-label, else the text.
        The address and the fields come from the button's form on the page,
        and the button's own name/value is sent too. `lands_on` is the page
        the redirect must go to; the list by default.
        """
        pairs = [
            (form, button)
            for form in page_forms(page)
            for button in form.buttons
            if button.accessible_name == button_text
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
        landing = lands_on or reverse("todo_list")
        self.assertEqual(response.redirect_chain, [(landing, 302)])
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

    def test_a_weekly_todo_comes_back(self):
        page = self.client.get(reverse("todo_list"))

        # Add a weekly to-do: choose "Every week" in the Repeats box.
        page = self.press(
            page,
            "Add",
            title="Take out the rubbish",
            due_date="2026-10-12",
            repeat="weekly",
        )
        rubbish = Todo.objects.get()
        row = todo_row(rubbish, repeat="Every week")
        self.assertIn('<small class="due">due 12 Oct 2026</small>', row)
        self.assert_list(page, row)

        # Done: it is completed, and a new one comes, due a week later.
        page = self.press(page, "Done")
        rubbish.refresh_from_db()
        [next_one] = Todo.objects.filter(done=False)
        self.assertEqual(rubbish.next_todo, next_one)
        self.assertEqual(next_one.title, "Take out the rubbish")
        next_row = todo_row(next_one, repeat="Every week")
        self.assertIn('<small class="due">due 19 Oct 2026</small>', next_row)
        self.assert_list(page, todo_row(rubbish, done=True))
        self.assert_list(page, next_row)

        # Undo on the completed one: the new one goes, the old one is open again.
        page = self.press(page, "Undo")
        self.assertEqual(list(Todo.objects.all()), [rubbish])
        self.assert_list(page, row)
        self.assertEqual(page_parts(page).titles, ["Take out the rubbish"])

    def test_split_a_todo_into_steps(self):
        page = self.client.get(reverse("todo_list"))
        page = self.press(page, "Add", title="Bake a cake")
        cake = Todo.objects.get()
        steps_url = f"/{cake.pk}/subtasks/"

        # The first step is found through Edit, then Steps.
        page = self.client.get(link_href(page, "Edit Bake a cake"))
        page = self.client.get(link_href(page, "Steps"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "<h1>Steps: Bake a cake</h1>", html=True)

        page = self.press(page, "Add step", lands_on=steps_url, title="Buy flour")
        page = self.press(page, "Add step", lands_on=steps_url, title="Bake")
        self.assertContains(page, '<span class="title">Buy flour</span>', html=True)
        self.assertContains(page, '<span class="title">Bake</span>', html=True)

        page = self.press(page, "Done Buy flour", lands_on=steps_url)
        names = [b.accessible_name for form in page_forms(page) for b in form.buttons]
        self.assertEqual(
            names,
            [
                "Undo Buy flour",
                "Delete Buy flour",
                "Done Bake",
                "Delete Bake",
                "Add step",
            ],
        )

        # Back on the list: "1 of 2 steps", and the to-do itself is still open.
        page = self.client.get(link_href(page, "Back to the list"))
        progress = (
            f'<a class="progress" href="{steps_url}" '
            'aria-label="1 of 2 steps for Bake a cake">1 of 2 steps</a>'
        )
        self.assert_list(page, todo_row(cake, progress=progress))
