from datetime import date

from django.test import TestCase
from django.urls import reverse

from todos.models import Todo


class TodoTests(TestCase):
    def test_list_page_loads(self):
        response = self.client.get(reverse("todo_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing to do yet")

    def test_add_a_todo(self):
        self.client.post(reverse("todo_add"), {"title": "Buy milk"})
        self.assertEqual(Todo.objects.get().title, "Buy milk")

    def test_empty_title_is_not_added(self):
        self.client.post(reverse("todo_add"), {"title": "   "})
        self.assertEqual(Todo.objects.count(), 0)

    def test_toggle_marks_done_and_back(self):
        todo = Todo.objects.create(title="Read chapter 3")
        self.client.post(reverse("todo_toggle", args=[todo.pk]))
        todo.refresh_from_db()
        self.assertTrue(todo.done)
        self.client.post(reverse("todo_toggle", args=[todo.pk]))
        todo.refresh_from_db()
        self.assertFalse(todo.done)

    def test_delete_removes_it(self):
        todo = Todo.objects.create(title="Call home")
        self.client.post(reverse("todo_delete", args=[todo.pk]))
        self.assertEqual(Todo.objects.count(), 0)

    def test_get_cannot_change_data(self):
        todo = Todo.objects.create(title="Call home")
        for url in [
            reverse("todo_add") + "?title=Buy+milk",
            reverse("todo_toggle", args=[todo.pk]),
            reverse("todo_delete", args=[todo.pk]),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 405)
        todo.refresh_from_db()
        self.assertFalse(todo.done)
        self.assertEqual(Todo.objects.count(), 1)

    def test_toggle_missing_todo_is_404(self):
        response = self.client.post(reverse("todo_toggle", args=[999]))
        self.assertEqual(response.status_code, 404)

    def test_delete_missing_todo_is_404(self):
        response = self.client.post(reverse("todo_delete", args=[999]))
        self.assertEqual(response.status_code, 404)

    # Due date: new behaviour.

    def test_add_a_todo_with_a_due_date(self):
        self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "due_date": "2026-10-12"}
        )
        self.assertEqual(Todo.objects.get().due_date, date(2026, 10, 12))

    def test_add_a_todo_without_a_due_date(self):
        self.client.post(reverse("todo_add"), {"title": "Buy milk"})
        todo = Todo.objects.get()
        self.assertEqual(todo.title, "Buy milk")
        self.assertIsNone(todo.due_date)

    def test_bad_due_date_is_not_added(self):
        self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "due_date": "not-a-date"}
        )
        self.assertEqual(Todo.objects.count(), 0)

    def test_bad_due_date_shows_an_error_and_keeps_the_title(self):
        response = self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "due_date": "not-a-date"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid date.")
        self.assertContains(response, 'value="Buy milk"')

    def test_us_style_date_is_not_accepted(self):
        self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "due_date": "12/10/2026"}
        )
        self.assertEqual(Todo.objects.count(), 0)

    def test_title_over_200_chars_is_not_added(self):
        self.client.post(reverse("todo_add"), {"title": "a" * 201})
        self.assertEqual(Todo.objects.count(), 0)

    def test_list_page_has_a_date_box(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, 'type="date"')

    def test_due_date_is_shown_on_the_list(self):
        Todo.objects.create(title="Buy milk", due_date=date(2026, 10, 12))
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, "due 12 Oct 2026")

    # Due date: protect what already works.

    def test_title_is_trimmed(self):
        self.client.post(reverse("todo_add"), {"title": "  Buy milk  "})
        self.assertEqual(Todo.objects.get().title, "Buy milk")

    def test_no_due_date_shows_no_due_text(self):
        Todo.objects.create(title="Buy milk")
        response = self.client.get(reverse("todo_list"))
        # ">due " is the start of the date text in the list. Plain "due " would
        # also match the page's CSS, so look for the text right after its tag.
        self.assertNotContains(response, ">due ")
