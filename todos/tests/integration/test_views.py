from datetime import date

from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from todos.models import Subtask, Todo
from todos.tests.integration.helpers import (
    LoggedInTestCase,
    page_forms,
    page_without_csrf,
)


class TodoTests(LoggedInTestCase):
    def test_list_page_loads(self):
        response = self.client.get(self.list_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing to do yet")

    def test_add_form_fields_have_accessible_names(self):
        # A screen reader reads these names. The old browser journey found the
        # fields by them, so a test must still check them exactly.
        page = page_without_csrf(self.client.get(self.list_url()))
        title = (
            '<input type="text" name="title" aria-label="New to-do" '
            'placeholder="What needs doing?" autofocus maxlength="200" required '
            'id="id_title">'
        )
        due_date = (
            '<label for="id_due_date">Due date (optional):</label>'
            '<input type="date" name="due_date" id="id_due_date">'
        )
        self.assertInHTML(title, page, count=1)
        self.assertInHTML(due_date, page, count=1)

    def test_add_a_todo(self):
        self.client.post(self.add_url(), {"title": "Buy milk"})
        self.assertEqual(Todo.objects.get().title, "Buy milk")

    def test_empty_title_is_not_added(self):
        self.client.post(self.add_url(), {"title": "   "})
        self.assertEqual(Todo.objects.count(), 0)

    def test_toggle_marks_done_and_back(self):
        todo = self.make_todo(title="Read chapter 3")
        self.client.post(reverse("todo_toggle", args=[todo.pk]), {"done": "1"})
        todo.refresh_from_db()
        self.assertTrue(todo.done)
        self.client.post(reverse("todo_toggle", args=[todo.pk]), {"done": "0"})
        todo.refresh_from_db()
        self.assertFalse(todo.done)

    def test_delete_removes_it(self):
        todo = self.make_todo(title="Call home")
        self.client.post(reverse("todo_delete", args=[todo.pk]))
        self.assertEqual(Todo.objects.count(), 0)

    def test_get_cannot_change_data(self):
        todo = self.make_todo(title="Call home")
        for url in [
            self.add_url() + "?title=Buy+milk",
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
        response = self.client.post(reverse("todo_toggle", args=[999]), {"done": "1"})
        self.assertEqual(response.status_code, 404)

    def test_delete_missing_todo_is_404(self):
        response = self.client.post(reverse("todo_delete", args=[999]))
        self.assertEqual(response.status_code, 404)

    # Due date: new behaviour.

    def test_add_a_todo_with_a_due_date(self):
        self.client.post(
            self.add_url(), {"title": "Buy milk", "due_date": "2026-10-12"}
        )
        self.assertEqual(Todo.objects.get().due_date, date(2026, 10, 12))

    def test_add_a_todo_without_a_due_date(self):
        self.client.post(self.add_url(), {"title": "Buy milk"})
        todo = Todo.objects.get()
        self.assertEqual(todo.title, "Buy milk")
        self.assertIsNone(todo.due_date)

    def test_bad_due_date_is_not_added(self):
        self.client.post(
            self.add_url(), {"title": "Buy milk", "due_date": "not-a-date"}
        )
        self.assertEqual(Todo.objects.count(), 0)

    def test_bad_due_date_shows_an_error_and_keeps_the_title(self):
        response = self.client.post(
            self.add_url(), {"title": "Buy milk", "due_date": "not-a-date"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid date.")
        self.assertContains(response, 'value="Buy milk"')

    def test_us_style_date_is_not_accepted(self):
        self.client.post(
            self.add_url(), {"title": "Buy milk", "due_date": "12/10/2026"}
        )
        self.assertEqual(Todo.objects.count(), 0)

    def test_title_over_200_chars_is_not_added(self):
        response = self.client.post(self.add_url(), {"title": "a" * 201})
        self.assertEqual(Todo.objects.count(), 0)
        self.assertContains(
            response, "Ensure this value has at most 200 characters (it has 201)."
        )

    def test_empty_title_shows_an_error(self):
        response = self.client.post(self.add_url(), {"title": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")

    def test_error_page_still_shows_the_list(self):
        self.make_todo(title="Call home")
        response = self.client.post(
            self.add_url(), {"title": "Buy milk", "due_date": "not-a-date"}
        )
        self.assertContains(response, "Call home")
        self.assertTrue(response.context["form"].errors)

    def test_past_due_date_is_allowed(self):
        self.client.post(
            self.add_url(), {"title": "Buy milk", "due_date": "2000-01-01"}
        )
        self.assertEqual(Todo.objects.get().due_date, date(2000, 1, 1))

    def test_list_page_has_a_date_box(self):
        response = self.client.get(self.list_url())
        self.assertContains(
            response,
            '<input type="date" name="due_date" id="id_due_date">',
            html=True,
        )

    def test_due_date_is_shown_on_the_list(self):
        # A day with one digit: "5 Oct", not "05 Oct".
        self.make_todo(title="Buy milk", due_date=date(2026, 10, 5))
        response = self.client.get(self.list_url())
        self.assertContains(response, "due 5 Oct 2026")

    # Due date: protect what already works.

    def test_title_is_trimmed(self):
        self.client.post(self.add_url(), {"title": "  Buy milk  "})
        self.assertEqual(Todo.objects.get().title, "Buy milk")

    def test_no_due_date_shows_no_due_text(self):
        self.make_todo(title="Buy milk")
        response = self.client.get(self.list_url())
        self.assertNotContains(response, 'class="due"')


class CountTests(LoggedInTestCase):
    """How many to-dos are left, shown under the list."""

    def assertFooter(self, response, text, completed=()):
        """The whole footer is on the page once, exactly.

        A completed to-do also puts the delete-completed button in the footer,
        so `completed` names them.
        """
        footer = self.list_footer(text, [todo.pk for todo in completed])
        self.assertInHTML(footer, page_without_csrf(response), count=1)

    # Count: new behaviour.

    def test_count_is_shown_under_the_list(self):
        self.make_todo(title="Buy milk")
        self.make_todo(title="Call home")
        read = self.make_todo(title="Read chapter 3", done=True)
        response = self.client.get(self.list_url())
        self.assertFooter(response, "2 items left", completed=[read])

    def test_count_comes_after_the_list(self):
        self.make_todo(title="Buy milk")
        page = self.client.get(self.list_url()).content.decode()
        self.assertIn('class="count"', page)
        self.assertGreater(page.index('class="count"'), page.index("</ul>"))

    def test_count_says_item_for_one(self):
        self.make_todo(title="Buy milk")
        response = self.client.get(self.list_url())
        self.assertFooter(response, "1 item left")

    def test_count_says_items_for_zero(self):
        milk = self.make_todo(title="Buy milk", done=True)
        response = self.client.get(self.list_url())
        self.assertFooter(response, "0 items left", completed=[milk])

    def test_count_is_on_the_error_page(self):
        self.make_todo(title="Call home")
        response = self.client.post(
            self.add_url(), {"title": "Buy milk", "due_date": "not-a-date"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFooter(response, "1 item left")

    def test_count_follows_done_and_undo(self):
        first = self.make_todo(title="Buy milk")
        self.make_todo(title="Call home")
        toggle = reverse("todo_toggle", args=[first.pk])
        response = self.client.post(toggle, {"done": "1"}, follow=True)
        self.assertFooter(response, "1 item left", completed=[first])
        response = self.client.post(toggle, {"done": "0"}, follow=True)
        self.assertFooter(response, "2 items left")

    def test_the_database_does_the_counting(self):
        self.make_todo(title="Buy milk")
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.list_url())
        counts = [
            q["sql"]
            for q in queries.captured_queries
            if "COUNT(" in q["sql"].upper() and "todos_todo" in q["sql"]
        ]
        self.assertTrue(counts, "the page should ask the database to COUNT the to-dos")

    # Count: protect what already works.

    def test_no_count_when_the_list_is_empty(self):
        response = self.client.get(self.list_url())
        self.assertContains(response, "Nothing to do yet")
        self.assertNotContains(response, "item left")
        self.assertNotContains(response, "items left")
        self.assertNotContains(response, 'class="count"')
        self.assertNotContains(response, 'class="list-footer"')


class DeleteCompletedTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.milk = self.make_todo(title="Buy milk", done=True)
        self.home = self.make_todo(title="Call home", done=True)
        self.read = self.make_todo(title="Read chapter 3")

    def post_ids(self, ids, client=None):
        return (client or self.client).post(self.delete_completed_url(), {"ids": ids})

    def titles(self):
        return set(Todo.objects.values_list("title", flat=True))

    # Delete completed: new behaviour.

    def test_delete_completed_removes_the_completed_ones_seen(self):
        response = self.post_ids([self.milk.pk, self.home.pk])
        self.assertRedirects(response, self.list_url())
        self.assertEqual(self.titles(), {"Read chapter 3"})

    def test_completed_after_the_page_loaded_survives(self):
        # The page showed only "Buy milk" as completed. "Call home" became
        # completed later, in another browser, so its id was not sent.
        self.post_ids([self.milk.pk])
        self.assertEqual(self.titles(), {"Call home", "Read chapter 3"})

    def test_open_todo_is_never_deleted(self):
        self.post_ids([self.read.pk])
        self.assertEqual(Todo.objects.count(), 3)

    def test_bad_ids_are_ignored(self):
        # 19 digits can be too big for SQLite's 64-bit integer: OverflowError,
        # a 500 page. This pins the 18-digit cap in the view.
        too_long = ["9" * 19, "9" * 30]
        response = self.post_ids(["abc", "", "²", *too_long, str(self.milk.pk)])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.titles(), {"Call home", "Read chapter 3"})

    def test_delete_completed_uses_a_fixed_number_of_queries(self):
        """The same few queries for 2 to-dos as for 5. Never one per to-do.

        Changed on purpose by repeating (19) and by steps (15). Django first
        reads the to-dos to delete, in ONE select (whole rows, all at once).
        The next_todo link (SET_NULL, 19) is emptied in ONE update. Steps (15)
        point to a to-do with CASCADE: all their steps go in ONE delete, and
        are never loaded. Then the to-dos go in ONE delete. It must never be
        one query per to-do or per step.
        """
        open_step = Subtask.objects.create(todo=self.read, title="Open page")
        more = [self.make_todo(title=f"Done {n}", done=True) for n in range(3)]
        for todo in [self.milk, self.home, *more]:
            for n in range(2):
                Subtask.objects.create(todo=todo, title=f"Step {n}")
        cases = [
            ("2 ids", [self.milk, self.home]),
            ("5 ids", [self.milk, self.home, *more]),
        ]
        sizes = []
        for label, todos in cases:
            with self.subTest(label):
                with transaction.atomic():
                    with CaptureQueriesContext(connection) as queries:
                        self.post_ids([todo.pk for todo in todos])
                    sqls = [query["sql"].strip().upper() for query in queries]
                    sizes.append(len(sqls))

                    def count(start, inside="", sqls=sqls):
                        return len(
                            [s for s in sqls if s.startswith(start) and inside in s]
                        )

                    # Steps: one DELETE for all of them, never a SELECT.
                    self.assertEqual(count('DELETE FROM "TODOS_SUBTASK" WHERE'), 1)
                    self.assertEqual(count("SELECT", 'FROM "TODOS_SUBTASK"'), 0)
                    # To-dos: one SELECT, one UPDATE (19's next_todo), one DELETE.
                    self.assertEqual(count("SELECT", 'FROM "TODOS_TODO"'), 1)
                    self.assertEqual(count('UPDATE "TODOS_TODO" SET "NEXT_TODO_ID"'), 1)
                    self.assertEqual(count("UPDATE"), 1)
                    self.assertEqual(count('DELETE FROM "TODOS_TODO" WHERE'), 1)
                    # The deleted to-dos' steps are gone; the open one's stays.
                    self.assertFalse(
                        Todo.objects.filter(pk__in=[t.pk for t in todos]).exists()
                    )
                    self.assertFalse(Subtask.objects.filter(todo__in=todos).exists())
                    self.assertTrue(Subtask.objects.filter(pk=open_step.pk).exists())
                    transaction.set_rollback(True)
        self.assertEqual(sizes[0], sizes[1])

    def test_get_cannot_delete_completed(self):
        response = self.client.get(self.delete_completed_url())
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Todo.objects.count(), 3)

    def test_delete_completed_needs_the_csrf_token(self):
        response = self.post_ids(
            [self.milk.pk, self.home.pk], client=self.csrf_client()
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Todo.objects.count(), 3)

    def test_the_form_on_the_page_works_with_csrf_checks_on(self):
        # Like a real browser: read the form from the page, then send it back.
        # This fails if the form has no {% csrf_token %}.
        client = self.csrf_client()
        page = client.get(self.list_url())
        [(form, button)] = [
            (form, button)
            for form in page_forms(page)
            for button in form.buttons
            if button.text == "Delete 2 completed to-dos"
        ]
        self.assertIn("csrfmiddlewaretoken", form.fields)
        # Both ids are sent, not only the last one.
        self.assertEqual(form.fields["ids"], [str(self.milk.pk), str(self.home.pk)])
        response = client.post(form.action, form.data(button))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.titles(), {"Read chapter 3"})

    def test_delete_completed_form_on_the_list(self):
        response = self.client.get(self.list_url())
        form = self.delete_completed_form([self.milk.pk, self.home.pk])
        self.assertInHTML(form, page_without_csrf(response), count=1)

    def test_delete_completed_form_is_in_the_list_footer(self):
        # The footer under the list is a <div>, not a <footer>: a <footer> in
        # <body> is announced to screen readers as the footer of the page.
        response = self.client.get(self.list_url())
        footer = self.list_footer("1 item left", [self.milk.pk, self.home.pk])
        self.assertInHTML(footer, page_without_csrf(response), count=1)

    def test_delete_completed_button_says_one_to_do(self):
        self.home.delete()
        response = self.client.get(self.list_url())
        form = self.delete_completed_form([self.milk.pk])
        self.assertIn("Delete 1 completed to-do</button>", form)
        self.assertInHTML(form, page_without_csrf(response), count=1)

    def test_at_most_500_are_offered_at_once(self):
        # Django refuses a form with more than 1,000 fields, and then nothing
        # is deleted. So the page offers the oldest 500; the next click
        # deletes the rest.
        Todo.objects.bulk_create(
            Todo(
                title=f"Done {n}", done=True, owner=self.user, todo_list=self.todo_list
            )
            for n in range(499)
        )
        oldest_first = list(
            Todo.objects.filter(done=True)
            .order_by("created_at", "pk")
            .values_list("pk", flat=True)
        )
        self.assertEqual(len(oldest_first), 501)
        self.assertEqual(oldest_first[0], self.milk.pk)

        response = self.client.get(self.list_url())
        footer = self.list_footer("1 item left", oldest_first[:500])
        self.assertInHTML(footer, page_without_csrf(response), count=1)

        response = self.post_ids(oldest_first[:500], client=self.client)
        self.assertEqual(response.status_code, 302)
        response = self.client.get(self.list_url())
        footer = self.list_footer("1 item left", oldest_first[500:])
        self.assertInHTML(footer, page_without_csrf(response), count=1)

    # Delete completed: protect what already works.

    def test_no_delete_completed_form_when_nothing_is_completed(self):
        Todo.objects.filter(done=True).delete()
        response = self.client.get(self.list_url())
        # The whole footer, exactly: the count, and no form.
        self.assertInHTML(
            self.list_footer("1 item left"), page_without_csrf(response), count=1
        )
