import re
from datetime import date
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from todos.forms import TodoEditForm
from todos.models import Todo
from todos.tests.integration.helpers import (
    page_forms,
    page_parts,
    page_without_csrf,
    pane_element,
    show_date,
    title_element,
    toggle_form,
)


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


class EditPriorityAndNotesTests(TestCase):
    """Priority (6) and notes (7) on the edit page: they come from TodoForm."""

    def setUp(self):
        self.todo = Todo.objects.create(
            title="Buy milk",
            due_date=date(2026, 10, 12),
            priority=Todo.Priority.HIGH,
            notes="2 litres",
        )
        self.url = reverse("todo_edit", args=[self.todo.pk])

    def assert_saved(self, **values):
        self.todo.refresh_from_db()
        for name, value in values.items():
            with self.subTest(field=name):
                self.assertEqual(getattr(self.todo, name), value)

    def edit_page_form(self):
        """The edit page's one POST form, read like a browser reads it."""
        page = self.client.get(self.url)
        (form,) = [form for form in page_forms(page) if form.method == "post"]
        return form

    def test_edit_page_shows_saved_priority_and_notes(self):
        response = self.client.get(self.url)
        self.assertContains(
            response,
            '<select name="priority" id="id_priority">'
            '<option value="3" selected>High</option>'
            '<option value="2">Medium</option>'
            '<option value="1">Low</option>'
            "</select>",
            html=True,
        )
        self.assertContains(response, '<label for="id_notes">Notes:</label>', html=True)
        # A visible label, so no aria-label on the box.
        self.assertContains(
            response,
            '<textarea name="notes" cols="40" rows="3" maxlength="500" id="id_notes">'
            "2 litres</textarea>",
            html=True,
        )

    def test_edit_saves_notes_and_priority(self):
        cases = [
            ("new notes", {"notes": "1 litre"}, {"notes": "1 litre"}),
            ("empty notes", {"notes": ""}, {"notes": ""}),
            ("a new priority", {"priority": "1"}, {"priority": Todo.Priority.LOW}),
        ]
        for name, posted, saved in cases:
            with self.subTest(name):
                data = {"title": "Buy milk", "priority": "3", "notes": "2 litres"}
                self.client.post(self.url, {**data, **posted})
                self.assert_saved(**saved)

    def test_editing_only_the_title_keeps_the_rest(self):
        # Send exactly what the edit page's form sends, with a new title.
        Todo.objects.filter(pk=self.todo.pk).update(notes="2 litres\nfull fat")
        form = self.edit_page_form()
        self.client.post(form.action, form.data(title="Buy oat milk"))
        self.assert_saved(
            title="Buy oat milk",
            due_date=date(2026, 10, 12),
            priority=Todo.Priority.HIGH,
            notes="2 litres\nfull fat",
        )

    def test_fields_left_out_of_a_post(self):
        # A hand-made post with only a title. A browser never sends this; the
        # test records Django's rules, so a change is seen.
        self.client.post(self.url, {"title": "Buy oat milk"})
        self.assert_saved(
            title="Buy oat milk",
            due_date=None,  # no model default: removed
            notes="2 litres",  # the model has default="": kept
            priority=Todo.Priority.MEDIUM,  # the priority rule: missing is Medium
        )

    # The three tests the notes plan (7) gave to this feature.

    def test_edit_changes_the_notes(self):
        self.client.post(self.url, {"title": "Buy milk", "notes": "Soy\r\nOr oat"})
        self.assert_saved(notes="Soy\nOr oat")

    def test_edit_can_empty_the_notes(self):
        self.client.post(self.url, {"title": "Buy milk", "notes": ""})
        self.assert_saved(notes="")

    def test_edit_title_keeps_the_notes(self):
        # The notes as the edit page sends them.
        form = self.edit_page_form()
        self.assertEqual(form.fields["notes"], ["2 litres"])
        self.client.post(form.action, form.data(title="Buy oat milk"))
        self.assert_saved(title="Buy oat milk", notes="2 litres")


class EditLinkPlaceTests(TestCase):
    """Where the Edit links are: on each row, and in the details pane."""

    def setUp(self):
        self.todo = Todo.objects.create(
            title="Buy milk", due_date=date(2026, 10, 12), priority=Todo.Priority.HIGH
        )

    def test_edit_link_is_right_before_done(self):
        # The whole row, exactly: the title span (link, priority, due date),
        # then Edit, then Done, then Delete.
        pk = self.todo.pk
        row = (
            f'<li id="todo-{pk}" class="">'
            f"{title_element(self.todo)}"
            f'<a class="edit" href="/{pk}/edit/" aria-label="Edit Buy milk">Edit</a>'
            f"{toggle_form(self.todo)}"
            f'<form method="post" action="/{pk}/delete/">'
            '<button type="submit">Delete</button></form>'
            "</li>"
        )
        response = self.client.get(reverse("todo_list"))
        self.assertInHTML(row, page_without_csrf(response), count=1)

    def test_pane_has_an_edit_link(self):
        pk = self.todo.pk
        response = self.client.get(f"/?show=active&selected={pk}")
        pane = pane_element(
            self.todo,
            due="12 Oct 2026",
            priority="High",
            created=show_date(timezone.localtime(self.todo.created_at).date()),
            edit_url=f"/{pk}/edit/?show=active&selected={pk}",
            close_url="/?show=active",
        )
        self.assertContains(response, pane, count=1, html=True)

    def test_save_from_the_pane_keeps_it_open(self):
        pk = self.todo.pk
        url = reverse("todo_edit", args=[pk]) + f"?show=active&selected={pk}"
        response = self.client.post(url, {"title": "Buy oat milk", "priority": "3"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/?show=active&selected={pk}")
