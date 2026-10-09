import re
from datetime import date
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from todos.forms import TodoEditForm
from todos.models import Todo
from todos.tests.integration.helpers import page_parts


def title_box(value, error=False):
    """The edit page's title box, exactly, with `value` in it.

    It has a visible label, so no aria-label and no placeholder. A box with an
    error points to its error list.
    """
    invalid = ' aria-invalid="true" aria-describedby="id_title_error"' if error else ""
    return (
        f'<input type="text" name="title" value="{value}" maxlength="200" required'
        f'{invalid} id="id_title" autofocus>'
    )


def error_list(field, message):
    """One field's error list, exactly."""
    return f'<ul class="errorlist" id="id_{field}_error"><li>{message}</li></ul>'


def edit_link(todo, aria_title, query=""):
    """The Edit link on a list row, exactly."""
    return (
        f'<a class="edit" href="/{todo.pk}/edit/{query}" '
        f'aria-label="Edit {aria_title}">Edit</a>'
    )


class EditTests(TestCase):
    def setUp(self):
        self.todo = Todo.objects.create(title="Buy milk", due_date=date(2026, 10, 12))

    def edit_url(self, query="", pk=None):
        return reverse("todo_edit", args=[pk or self.todo.pk]) + query

    def assert_not_changed(self):
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.title, "Buy milk")
        self.assertEqual(self.todo.due_date, date(2026, 10, 12))

    # Edit: new behaviour.

    def test_edit_page_shows_the_saved_values(self):
        response = self.client.get(self.edit_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Edit to-do</title>", html=True)
        self.assertContains(response, "<h1>Edit to-do</h1>", html=True)
        self.assertContains(response, '<label for="id_title">Title:</label>', html=True)
        self.assertContains(response, title_box("Buy milk"), html=True)
        self.assertContains(
            response,
            '<input type="date" name="due_date" value="2026-10-12" id="id_due_date">',
            html=True,
        )

    def test_edit_saves_the_new_values(self):
        response = self.client.post(
            self.edit_url(), {"title": "Buy oat milk", "due_date": "2026-10-20"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.title, "Buy oat milk")
        self.assertEqual(self.todo.due_date, date(2026, 10, 20))

    def test_edit_can_remove_the_due_date(self):
        self.client.post(self.edit_url(), {"title": "Buy milk", "due_date": ""})
        self.todo.refresh_from_db()
        self.assertIsNone(self.todo.due_date)

    def test_bad_edit_is_not_saved_and_keeps_the_input(self):
        long_title = "a" * 201
        cases = [
            (
                {"title": "   ", "due_date": "2026-10-12"},
                error_list("title", "This field is required."),
                title_box("   ", error=True),
            ),
            (
                {"title": long_title, "due_date": "2026-10-12"},
                error_list(
                    "title",
                    "Ensure this value has at most 200 characters (it has 201).",
                ),
                title_box(long_title, error=True),
            ),
            (
                {"title": "Buy oat milk", "due_date": "not-a-date"},
                error_list("due_date", "Enter a valid date."),
                title_box("Buy oat milk"),
            ),
        ]
        for data, error, box in cases:
            with self.subTest(data=data):
                response = self.client.post(self.edit_url(), data)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error, html=True)
                self.assertContains(response, box, html=True)
                self.assert_not_changed()

    def test_bad_edit_never_shows_the_unsaved_title(self):
        # The title is good and the date is bad: Django puts the new title in
        # the to-do in memory, but it is not saved. Only the box may show it.
        response = self.client.post(
            self.edit_url(), {"title": "Buy oat milk", "due_date": "not-a-date"}
        )
        self.assertContains(response, "<title>Edit to-do</title>", html=True)
        self.assertContains(response, "<h1>Edit to-do</h1>", html=True)
        self.assertContains(response, "Buy oat milk", count=1)

    def test_edit_does_not_change_done_or_created_at(self):
        cases = [
            ("a completed to-do, posted without done", True, {}),
            ("an open to-do, posted with done=on", False, {"done": "on"}),
        ]
        for name, done, extra in cases:
            with self.subTest(name):
                todo = Todo.objects.create(title="Call home", done=done)
                created_at = todo.created_at
                self.client.post(
                    self.edit_url(pk=todo.pk), {"title": "Call mum", **extra}
                )
                todo.refresh_from_db()
                self.assertEqual(todo.title, "Call mum")
                self.assertEqual(todo.done, done)
                self.assertEqual(todo.created_at, created_at)

    def test_get_edit_page_changes_nothing(self):
        self.client.get(self.edit_url("?title=Hacked"))
        self.assert_not_changed()

    def test_edit_missing_todo_is_404(self):
        url = reverse("todo_edit", args=[999])
        for method in ["get", "post"]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, {"title": "Hacked"})
                self.assertEqual(response.status_code, 404)

    def test_edit_allows_only_get_head_and_post(self):
        for method, status in [("head", 200), ("put", 405), ("delete", 405)]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.edit_url())
                self.assertEqual(response.status_code, status)
                self.assert_not_changed()

    def test_list_has_an_edit_link_for_each_todo(self):
        tricky = Todo.objects.create(title='Say "hi" <b>')
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, edit_link(self.todo, "Buy milk"), html=True)
        self.assertContains(
            response,
            edit_link(tricky, "Say &quot;hi&quot; &lt;b&gt;"),
            html=True,
        )

    def test_edit_link_keeps_the_filter(self):
        response = self.client.get(reverse("todo_list") + "?show=active")
        self.assertContains(
            response, edit_link(self.todo, "Buy milk", "?show=active"), html=True
        )

    def test_edit_page_keeps_the_filter(self):
        for query in ["", "?show=active"]:
            with self.subTest(query=query):
                response = self.client.get(self.edit_url(query))
                self.assertEqual(
                    page_parts(response).post_actions, [f"/{self.todo.pk}/edit/{query}"]
                )
                self.assertContains(
                    response, f'<a href="/{query}">Cancel</a>', html=True
                )

    def test_save_keeps_the_filter(self):
        url = self.edit_url("?show=completed")
        with self.subTest("a good post"):
            response = self.client.post(url, {"title": "Buy oat milk"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "/?show=completed")
        with self.subTest("a post with an empty title"):
            response = self.client.post(url, {"title": ""})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                page_parts(response).post_actions,
                [f"/{self.todo.pk}/edit/?show=completed"],
            )

    def test_hostile_params_never_reach_an_address(self):
        hostile = "?show=//evil.example&next=https://evil.example"
        url = self.edit_url(hostile)
        with self.subTest("the edit page"):
            response = self.client.get(url)
            self.assertEqual(
                page_parts(response).post_actions, [f"/{self.todo.pk}/edit/"]
            )
            self.assertContains(response, '<a href="/">Cancel</a>', html=True)
        with self.subTest("a good post"):
            response = self.client.post(url, {"title": "Buy oat milk"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "/")

    def test_todo_deleted_while_saving_is_not_brought_back(self):
        # Someone deletes the to-do after the form was checked and before it is
        # saved. The save must not make the to-do again.
        real_is_valid = TodoEditForm.is_valid

        def is_valid_then_deleted(form):
            valid = real_is_valid(form)
            Todo.objects.filter(pk=form.instance.pk).delete()
            return valid

        with patch.object(TodoEditForm, "is_valid", is_valid_then_deleted):
            response = self.client.post(self.edit_url(), {"title": "Buy oat milk"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Todo.objects.exists())

    # Protecting: these pass before the change, and must still pass after.

    def test_every_page_has_the_shared_head(self):
        for name, url in [("list", reverse("todo_list")), ("edit", self.edit_url())]:
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertContains(response, '<meta charset="utf-8">', html=True)
                self.assertContains(
                    response,
                    '<meta name="viewport" '
                    'content="width=device-width, initial-scale=1">',
                    html=True,
                )
                self.assertContains(
                    response, '<link rel="icon" href="data:,">', html=True
                )
                self.assertEqual(page_parts(response).html_lang, "en")

    def test_edit_needs_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.edit_url(), {"title": "Hacked"})
        self.assertEqual(response.status_code, 403)
        self.assert_not_changed()

    def test_the_edit_form_works_with_csrf_checks_on(self):
        # Like a real browser: read the token from the page, then send it back.
        # This fails if the edit form has no {% csrf_token %}.
        client = Client(enforce_csrf_checks=True)
        page = client.get(self.edit_url()).content.decode()
        form = re.search(r'<form class="edit".*?</form>', page, re.S)
        self.assertIsNotNone(form, "the page has no edit form")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form[0])
        self.assertIsNotNone(token, "the edit form has no CSRF token")
        response = client.post(
            self.edit_url(),
            {"csrfmiddlewaretoken": token[1], "title": "Buy oat milk"},
        )
        self.assertEqual(response.status_code, 302)
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.title, "Buy oat milk")

    def test_list_page_keeps_its_title_and_add_form(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, "<title>To-do list</title>", html=True)
        self.assertContains(response, "<h1>To-do list</h1>", html=True)
        self.assertContains(
            response,
            '<input type="text" name="title" aria-label="New to-do" '
            'placeholder="What needs doing?" autofocus maxlength="200" required '
            'id="id_title">',
            html=True,
        )
