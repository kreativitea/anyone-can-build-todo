from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from todos.models import Todo


class PageParts(HTMLParser):
    """Finds the POST forms and the chosen links on a page.

    `post_actions` is the `action` of every form with method="post".
    `current_links` is the text of every link with aria-current="page".
    """

    def __init__(self, html):
        super().__init__()
        self.post_actions = []
        self.current_links = []
        self._in_current_link = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and (attrs.get("method") or "").lower() == "post":
            self.post_actions.append(attrs.get("action", ""))
        if tag == "a" and attrs.get("aria-current") == "page":
            self.current_links.append("")
            self._in_current_link = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_current_link = False

    def handle_data(self, data):
        if self._in_current_link:
            self.current_links[-1] += data.strip()


def page_parts(response):
    return PageParts(response.content.decode())


class FilterTests(TestCase):
    def make_one_of_each(self):
        self.active = Todo.objects.create(title="Buy milk")
        self.completed = Todo.objects.create(title="Call home", done=True)

    # Filter: new behaviour.

    def test_active_shows_only_active_todos(self):
        self.make_one_of_each()
        response = self.client.get("/?show=active")
        self.assertContains(response, "Buy milk")
        self.assertNotContains(response, "Call home")

    def test_completed_shows_only_completed_todos(self):
        self.make_one_of_each()
        response = self.client.get("/?show=completed")
        self.assertContains(response, "Call home")
        self.assertNotContains(response, "Buy milk")

    def test_filter_links_are_on_the_page(self):
        response = self.client.get("/")
        self.assertContains(
            response, '<a href="/" aria-current="page">All</a>', html=True
        )
        self.assertContains(response, '<a href="/?show=active">Active</a>', html=True)
        self.assertContains(
            response, '<a href="/?show=completed">Completed</a>', html=True
        )

    def test_chosen_filter_is_marked(self):
        response = self.client.get("/?show=completed")
        self.assertContains(
            response,
            '<a href="/?show=completed" aria-current="page">Completed</a>',
            html=True,
        )
        # Only one link is chosen. (The CSS also has the words aria-current,
        # so count the links, not the text.)
        self.assertEqual(page_parts(response).current_links, ["Completed"])

    def test_unknown_filter_marks_all(self):
        response = self.client.get("/?show=banana")
        self.assertContains(
            response, '<a href="/" aria-current="page">All</a>', html=True
        )
        self.assertEqual(page_parts(response).current_links, ["All"])

    def test_empty_message_for_each_filter(self):
        with self.subTest(show="active"):
            Todo.objects.create(title="Call home", done=True)
            response = self.client.get("/?show=active")
            self.assertContains(response, "Nothing left to do.")
        Todo.objects.all().delete()
        with self.subTest(show="completed"):
            Todo.objects.create(title="Buy milk")
            response = self.client.get("/?show=completed")
            self.assertContains(response, "Nothing completed yet.")

    def test_every_post_form_keeps_the_filter(self):
        self.make_one_of_each()
        for show in ["active", "completed"]:
            with self.subTest(show=show):
                response = self.client.get(f"/?show={show}")
                actions = page_parts(response).post_actions
                # add, plus toggle and delete for the one to-do shown
                self.assertGreaterEqual(len(actions), 3)
                for action in actions:
                    self.assertTrue(
                        action.endswith(f"?show={show}"),
                        f"{action!r} does not keep ?show={show}",
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
            reverse("todo_toggle", args=[self.completed.pk]) + "?show=completed"
        )
        self.assertEqual(response["Location"], "/?show=completed")

    def test_toggle_on_active_leaves_the_list(self):
        todo = Todo.objects.create(title="Buy milk")
        response = self.client.post(
            reverse("todo_toggle", args=[todo.pk]) + "?show=active", follow=True
        )
        self.assertEqual(response.redirect_chain, [("/?show=active", 302)])
        self.assertNotContains(response, "Buy milk")
        self.assertContains(response, "Nothing left to do.")

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
        self.assertContains(response, "Buy milk")
        self.assertNotContains(response, "Call home")
        parts = page_parts(response)
        self.assertEqual(parts.current_links, ["Active"])
        self.assertGreaterEqual(len(parts.post_actions), 3)
        for action in parts.post_actions:
            self.assertTrue(action.endswith("?show=active"), action)

    def test_redirect_drops_unknown_params(self):
        self.make_one_of_each()
        response = self.client.post(
            reverse("todo_toggle", args=[self.active.pk])
            + "?show=active&next=https://evil.example"
        )
        self.assertEqual(response["Location"], "/?show=active")

    # Filter: protect what already works.

    def test_all_shows_every_todo(self):
        self.make_one_of_each()
        for url in ["/", "/?show=all"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "Buy milk")
                self.assertContains(response, "Call home")

    def test_unknown_filter_shows_every_todo(self):
        self.make_one_of_each()
        response = self.client.get("/?show=banana")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Buy milk")
        self.assertContains(response, "Call home")

    def test_post_without_query_goes_to_the_list(self):
        self.make_one_of_each()
        toggle = reverse("todo_toggle", args=[self.active.pk])
        for url in [toggle, toggle + "?show=all"]:
            with self.subTest(url=url):
                response = self.client.post(url)
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
                response = self.client.post(toggle + query, data)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/")
