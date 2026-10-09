"""Notes on a to-do (feature 7): the add form, saving, and the details pane."""

from django.urls import reverse
from django.utils import timezone

from todos.models import Todo
from todos.tests.integration.helpers import (
    LoggedInTestCase,
    page_parts,
    page_without_csrf,
    pane_element,
    show_date,
)

SUMMARY = "<summary>Notes (optional)</summary>"


def notes_textarea(text="", *, error=False):
    """The notes text box, exactly as Django 5.2 draws it."""
    invalid = ' aria-invalid="true" aria-describedby="id_notes_error"' if error else ""
    return (
        '<textarea name="notes" cols="40" rows="3" aria-label="Notes" '
        f'maxlength="500"{invalid} id="id_notes">{text}</textarea>'
    )


def notes_box(inside, *, is_open):
    """The whole folded notes box on the add form: open or closed."""
    open_attr = " open" if is_open else ""
    return f'<details class="add-notes"{open_attr}>{SUMMARY}{inside}</details>'


def pane_for(todo, notes=None):
    """The whole pane of `todo`, opened from "/": only fills in the keywords."""
    return pane_element(
        todo,
        status="Completed" if todo.done else "Active",
        due=show_date(todo.due_date) if todo.due_date else "No due date",
        priority=todo.get_priority_display(),
        created=show_date(timezone.localtime(todo.created_at).date()),
        close_url="/",
        notes=notes,
    )


def selected_page(client, todo):
    return client.get(f"/?selected={todo.pk}")


class NotesTests(LoggedInTestCase):
    # New behaviour: these fail before the change.

    def test_add_a_todo_with_notes(self):
        self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "notes": "Low-fat\r\nOr soy"}
        )
        self.assertEqual(Todo.objects.get().notes, "Low-fat\nOr soy")

    def test_add_a_todo_without_notes(self):
        self.client.post(reverse("todo_add"), {"title": "Buy milk"})
        todo = Todo.objects.get()
        self.assertEqual(todo.title, "Buy milk")
        self.assertEqual(todo.notes, "")

    def test_notes_over_the_limit_are_not_added(self):
        notes = "a" * 501
        response = self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "notes": notes}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Todo.objects.count(), 0)
        error_list = (
            '<ul class="errorlist" id="id_notes_error"><li>Ensure this value has '
            "at most 500 characters (it has 501).</li></ul>"
        )
        self.assertContains(
            response,
            notes_box(error_list + notes_textarea(notes, error=True), is_open=True),
            html=True,
        )

    def test_list_page_has_a_notes_box(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, notes_textarea(), html=True)
        self.assertContains(response, SUMMARY, html=True)

    def test_notes_box_is_closed_on_a_new_page(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(
            response, notes_box(notes_textarea(), is_open=False), html=True
        )

    def test_bad_date_keeps_the_notes(self):
        cases = [
            (
                "notes",
                "Ring Ana first",
                notes_box(notes_textarea("Ring Ana first"), is_open=True),
            ),
            # Notes of only spaces count as no notes: the box stays closed.
            ("only spaces", "   ", notes_box(notes_textarea("   "), is_open=False)),
        ]
        for name, notes, expected_box in cases:
            with self.subTest(name):
                response = self.client.post(
                    reverse("todo_add"),
                    {"title": "Buy milk", "due_date": "not-a-date", "notes": notes},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Todo.objects.count(), 0)
                self.assertContains(response, expected_box, html=True)

    def test_pane_shows_notes_with_line_breaks(self):
        # "\r\n" is how old data, or data saved from the shell, could look.
        for notes in ["Low-fat\nOr soy", "Low-fat\r\nOr soy"]:
            with self.subTest(notes=notes):
                todo = self.make_todo(title="Buy milk", notes=notes)
                response = selected_page(self.client, todo)
                self.assertContains(
                    response,
                    pane_for(todo, notes="Low-fat\nOr soy"),
                    count=1,
                    html=True,
                )
                self.assertEqual(page_parts(response).pane_notes, "Low-fat\nOr soy")

    def test_pane_notes_are_escaped(self):
        notes = "<script>alert(1)</script>"
        todo = self.make_todo(title="Buy milk", notes=notes)
        response = selected_page(self.client, todo)
        # pane_for escapes it: "&lt;script&gt;...", shown as text.
        self.assertContains(response, pane_for(todo, notes=notes), count=1, html=True)
        parts = page_parts(response)
        self.assertEqual(parts.pane_notes, notes)
        self.assertNotIn("script", parts.pane_tags)

    def test_notes_are_not_on_the_list(self):
        todo = self.make_todo(title="Buy milk", notes="Low-fat")
        with_notes = page_without_csrf(self.client.get("/"))
        Todo.objects.filter(pk=todo.pk).update(notes="")
        without_notes = page_without_csrf(self.client.get("/"))
        self.assertEqual(with_notes, without_notes)

    # Protects what already works: passes before the change too.

    def test_pane_without_notes_has_no_notes_row(self):
        todo = self.make_todo(title="Buy milk")
        response = selected_page(self.client, todo)
        self.assertContains(response, pane_for(todo), count=1, html=True)
        self.assertIsNone(page_parts(response).pane_notes)
