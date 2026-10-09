from django.urls import reverse

from todos.models import Todo
from todos.tests.integration.helpers import (
    LoggedInTestCase,
    list_footer,
    page_parts,
    page_without_csrf,
)

# The empty message for each filter, as the whole <li> element.
EMPTY_ALL = "<li>Nothing to do yet. Add something above.</li>"
EMPTY_ACTIVE = "<li>Nothing left to do.</li>"
EMPTY_COMPLETED = "<li>Nothing completed yet.</li>"
EMPTY_MESSAGES = [EMPTY_ALL, EMPTY_ACTIVE, EMPTY_COMPLETED]

# The filter links, as the whole <nav> element, for each chosen filter.
NAV = (
    '<nav class="filters" aria-labelledby="filter-label">'
    '<span id="filter-label">Show:</span>'
    '<a href="/"{all}>All</a>'
    '<a href="/?show=active"{active}>Active</a>'
    '<a href="/?show=completed"{completed}>Completed</a>'
    "</nav>"
)
CURRENT = ' aria-current="page"'


def nav(chosen):
    """The whole filter <nav>, with `chosen` ("all", "active" or "completed") marked."""
    marks = {"all": "", "active": "", "completed": ""}
    marks[chosen] = CURRENT
    return NAV.format(**marks)


class FilterTests(LoggedInTestCase):
    def make_one_of_each(self):
        self.active = self.make_todo(title="Buy milk")
        self.completed = self.make_todo(title="Call home", done=True)

    def forms_for(self, todo, query):
        """The exact actions of every POST form on the page, in order.

        The add form, the shown to-do's toggle and delete forms, and the
        delete-completed form in the footer (there is always a completed to-do
        in these tests, so it is always there).
        """
        return [
            reverse("todo_add") + query,
            reverse("todo_toggle", args=[todo.pk]) + query,
            reverse("todo_delete", args=[todo.pk]) + query,
            reverse("todo_delete_completed") + query,
        ]

    # Filter: new behaviour.

    def test_active_shows_only_active_todos(self):
        self.make_one_of_each()
        response = self.client.get("/?show=active")
        self.assertEqual(page_parts(response).titles, ["Buy milk"])

    def test_completed_shows_only_completed_todos(self):
        self.make_one_of_each()
        response = self.client.get("/?show=completed")
        self.assertEqual(page_parts(response).titles, ["Call home"])

    def test_filter_links_are_on_the_page(self):
        response = self.client.get("/")
        self.assertContains(response, nav("all"), count=1, html=True)

    def test_chosen_filter_is_marked(self):
        response = self.client.get("/?show=completed")
        self.assertContains(response, nav("completed"), count=1, html=True)
        self.assertEqual(page_parts(response).current_links, ["Completed"])

    def test_unknown_filter_marks_all(self):
        response = self.client.get("/?show=banana")
        self.assertContains(response, nav("all"), count=1, html=True)
        self.assertEqual(page_parts(response).current_links, ["All"])

    def test_empty_message_for_each_filter(self):
        with self.subTest(show="active"):
            self.make_todo(title="Call home", done=True)
            response = self.client.get("/?show=active")
            self.assertEqual(page_parts(response).titles, [])
            self.assertContains(response, EMPTY_ACTIVE, count=1, html=True)
        Todo.objects.all().delete()
        with self.subTest(show="completed"):
            self.make_todo(title="Buy milk")
            response = self.client.get("/?show=completed")
            self.assertEqual(page_parts(response).titles, [])
            self.assertContains(response, EMPTY_COMPLETED, count=1, html=True)

    def test_every_post_form_keeps_the_filter(self):
        self.make_one_of_each()
        for show, shown in [("active", self.active), ("completed", self.completed)]:
            with self.subTest(show=show):
                response = self.client.get(f"/?show={show}")
                self.assertEqual(
                    page_parts(response).post_actions,
                    self.forms_for(shown, f"?show={show}"),
                )

    def test_add_keeps_the_filter(self):
        response = self.client.post(
            reverse("todo_add") + "?show=active", {"title": "Buy milk"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/?show=active")

    def test_toggle_keeps_the_filter(self):
        self.make_one_of_each()
        response = self.client.post(
            reverse("todo_toggle", args=[self.completed.pk]) + "?show=completed",
            {"done": "0"},
        )
        self.assertEqual(response["Location"], "/?show=completed")

    def test_toggle_on_active_leaves_the_list(self):
        todo = self.make_todo(title="Buy milk")
        response = self.client.post(
            reverse("todo_toggle", args=[todo.pk]) + "?show=active",
            {"done": "1"},
            follow=True,
        )
        self.assertEqual(response.redirect_chain, [("/?show=active", 302)])
        self.assertEqual(page_parts(response).titles, [])
        self.assertContains(response, EMPTY_ACTIVE, count=1, html=True)

    def test_delete_keeps_the_filter(self):
        self.make_one_of_each()
        response = self.client.post(
            reverse("todo_delete", args=[self.completed.pk]) + "?show=completed"
        )
        self.assertEqual(response["Location"], "/?show=completed")

    def test_add_error_keeps_the_filter(self):
        self.make_one_of_each()
        response = self.client.post(
            reverse("todo_add") + "?show=active",
            {"title": "New", "due_date": "not-a-date"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid date.")
        parts = page_parts(response)
        self.assertEqual(parts.titles, ["Buy milk"])
        self.assertEqual(parts.current_links, ["Active"])
        self.assertEqual(
            parts.post_actions, self.forms_for(self.active, "?show=active")
        )

    def test_redirect_drops_unknown_params(self):
        self.make_one_of_each()
        response = self.client.post(
            reverse("todo_toggle", args=[self.active.pk])
            + "?show=active&next=https://evil.example",
            {"done": "1"},
        )
        self.assertEqual(response["Location"], "/?show=active")

    def test_no_empty_message_when_the_list_has_items(self):
        self.make_one_of_each()
        for url in ["/", "/?show=active", "/?show=completed"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                for message in EMPTY_MESSAGES:
                    self.assertNotContains(response, message, html=True)

    # Filter with count (12) and delete completed (11): the footer is about the
    # whole table, not only what the filter shows.

    def test_count_shows_on_completed_view_with_nothing_completed(self):
        self.make_todo(title="Buy milk")
        response = self.client.get("/?show=completed")
        self.assertEqual(page_parts(response).titles, [])
        self.assertContains(response, EMPTY_COMPLETED, count=1, html=True)
        self.assertInHTML(
            list_footer("1 item left"), page_without_csrf(response), count=1
        )

    def test_count_on_active_view_with_everything_completed(self):
        todo = self.make_todo(title="Call home", done=True)
        response = self.client.get("/?show=active")
        self.assertEqual(page_parts(response).titles, [])
        self.assertContains(response, EMPTY_ACTIVE, count=1, html=True)
        self.assertInHTML(
            list_footer("0 items left", [todo.pk], "?show=active"),
            page_without_csrf(response),
            count=1,
        )

    def test_delete_completed_keeps_the_filter(self):
        todo = self.make_todo(title="Call home", done=True)
        response = self.client.post(
            reverse("todo_delete_completed") + "?show=completed", {"ids": [todo.pk]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/?show=completed")
        self.assertFalse(Todo.objects.exists())

    # Filter: protect what already works.

    def test_all_shows_every_todo(self):
        self.make_one_of_each()
        for url in ["/", "/?show=all"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(page_parts(response).titles, ["Buy milk", "Call home"])

    def test_unknown_filter_shows_every_todo(self):
        self.make_one_of_each()
        response = self.client.get("/?show=banana")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(page_parts(response).titles, ["Buy milk", "Call home"])

    def test_empty_list_on_all_shows_the_old_message(self):
        response = self.client.get("/")
        self.assertEqual(page_parts(response).titles, [])
        self.assertContains(response, EMPTY_ALL, count=1, html=True)

    def test_post_without_query_goes_to_the_list(self):
        self.make_one_of_each()
        toggle = reverse("todo_toggle", args=[self.active.pk])
        for url in [toggle, toggle + "?show=all"]:
            with self.subTest(url=url):
                response = self.client.post(url, {"done": "1"})
                self.assertEqual(response["Location"], "/")

    def test_redirect_only_goes_to_the_list_page(self):
        self.make_one_of_each()
        toggle = reverse("todo_toggle", args=[self.active.pk])
        cases = [
            # (the query after the address, the posted data)
            ("?next=https://evil.example", {"next": "https://evil.example"}),
            ("?show=https://evil.example", {}),
            ("?show=//evil.example", {}),
            ("?show=completed%0D%0ALocation:%20https://evil.example", {}),
            ("?show=completed%26next%3Dhttps://evil.example", {}),
        ]
        for query, data in cases:
            with self.subTest(query=query):
                response = self.client.post(toggle + query, {**data, "done": "1"})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/")
