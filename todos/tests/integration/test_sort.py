from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from todos.models import Todo
from todos.tests.integration.helpers import page_parts, title_element

HIGH = Todo.Priority.HIGH
MEDIUM = Todo.Priority.MEDIUM
LOW = Todo.Priority.LOW

# The sort links, as the whole <nav> element. Each link is filled in by `nav`.
NAV = (
    '<nav class="sort" aria-label="Sort by">Sort by: '
    '<a href="/"{created}>Date added</a>'
    '<a href="/?sort=due"{due}>Due date</a>'
    '<a href="/?sort=priority"{priority}>Priority</a>'
    '<a href="/?sort=title"{title}>Title</a>'
    "</nav>"
)
CURRENT = ' aria-current="true"'


def nav(chosen):
    """The whole sort <nav> on a page with no other parameters, `chosen` marked."""
    marks = {"created": "", "due": "", "priority": "", "title": ""}
    marks[chosen] = CURRENT
    return NAV.format(**marks)


def make(title, **fields):
    return Todo.objects.create(title=title, **fields)


def make_earlier(todo, than):
    """Set `todo`'s date added to just before `than`'s.

    Then the id order and the date-added order disagree: a test that needs the
    date-added order cannot pass by the id order by chance.
    """
    earlier = than.created_at - timedelta(seconds=1)
    Todo.objects.filter(pk=todo.pk).update(created_at=earlier)


class SortTests(TestCase):
    def titles(self, url):
        """The titles on the page at `url`, in the order the page shows them."""
        return page_parts(self.client.get(url)).titles

    # Sort: new behaviour. In every order test, the to-do that should come
    # FIRST is made LAST, so the old order (oldest first) can never pass.

    def test_sort_by_due_date(self):
        make("No date")
        make("Later", due_date=date(2026, 10, 20))
        make("Soon", due_date=date(2026, 10, 12))
        self.assertEqual(self.titles("/?sort=due"), ["Soon", "Later", "No date"])

    def test_due_date_ties_go_high_priority_first(self):
        make("Low", due_date=date(2026, 10, 12), priority=LOW)
        make("High", due_date=date(2026, 10, 12), priority=HIGH)
        self.assertEqual(self.titles("/?sort=due"), ["High", "Low"])

    def test_sort_by_priority(self):
        make("Low", priority=LOW)
        make("Medium", priority=MEDIUM)
        make("High", priority=HIGH)
        self.assertEqual(self.titles("/?sort=priority"), ["High", "Medium", "Low"])

    def test_priority_ties_go_soonest_due_first(self):
        make("Low", priority=LOW)
        make("High no date", priority=HIGH)
        make("High later", priority=HIGH, due_date=date(2026, 10, 20))
        make("High soon", priority=HIGH, due_date=date(2026, 10, 12))
        self.assertEqual(
            self.titles("/?sort=priority"),
            ["High soon", "High later", "High no date", "Low"],
        )

    def test_sort_by_title_ignores_case(self):
        make("cherry")
        make("Banana")
        make("apple")
        self.assertEqual(self.titles("/?sort=title"), ["apple", "Banana", "cherry"])

    def test_title_ties_keep_date_added_order(self):
        b = make("Buy milk")
        a = make("buy milk")
        make_earlier(a, than=b)  # id order: B, A. Date added: A, B.
        make("apple")
        self.assertEqual(self.titles("/?sort=title"), ["apple", "buy milk", "Buy milk"])

    def test_sort_by_title_hiragana(self):
        make("うどん")
        make("いちご")
        make("あめ")
        self.assertEqual(self.titles("/?sort=title"), ["あめ", "いちご", "うどん"])

    def test_sort_links_are_on_the_page(self):
        response = self.client.get("/")
        self.assertContains(response, nav("created"), count=1, html=True)

    def test_chosen_sort_is_marked(self):
        for url, chosen in [
            ("/?sort=priority", "priority"),
            ("/?sort=banana", "created"),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, nav(chosen), count=1, html=True)
                # The filter's mark is not changed: only All has "page".
                self.assertEqual(page_parts(response).current_links, ["All"])

    def test_sort_is_kept_everywhere(self):
        todo = make("Buy milk")
        response = self.client.get("/?show=active&q=milk&sort=due")
        query = "?show=active&q=milk&sort=due"
        parts = [
            '<a href="/?show=active&amp;q=milk&amp;sort=due" '
            'aria-current="page">Active</a>',
            '<input type="hidden" name="sort" value="due">',
            '<a href="/?show=active&amp;sort=due">Clear search</a>',
            f'<a class="edit" href="/{todo.pk}/edit/?show=active&amp;q=milk&amp;'
            'sort=due" aria-label="Edit Buy milk">Edit</a>',
            '<a href="/?show=active&amp;q=milk&amp;sort=title">Title</a>',
            title_element(todo, query),
        ]
        for part in parts:
            with self.subTest(part=part):
                self.assertContains(response, part, count=1, html=True)

    def test_every_post_form_keeps_the_sort(self):
        active = make("Buy milk")
        make("Call home", done=True)
        query = "?show=active&sort=title"
        response = self.client.get("/" + query)
        self.assertEqual(
            page_parts(response).post_actions,
            [
                reverse("todo_add") + query,
                reverse("todo_toggle", args=[active.pk]) + query,
                reverse("todo_delete", args=[active.pk]) + query,
                reverse("todo_delete_completed") + query,
            ],
        )

    def test_post_goes_back_with_the_sort(self):
        query = "?show=active&sort=due"
        todo = make("Buy milk")
        other = make("Call home")
        cases = [
            ("toggle", reverse("todo_toggle", args=[todo.pk]), {}),
            ("delete", reverse("todo_delete", args=[other.pk]), {}),
            ("add", reverse("todo_add"), {"title": "New"}),
            (
                "edit",
                reverse("todo_edit", args=[todo.pk]),
                {"title": "Buy oat milk", "priority": MEDIUM},
            ),
        ]
        for name, url, data in cases:
            with self.subTest(name=name):
                response = self.client.post(url + query, data)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/" + query)

    def test_sort_filter_and_search_together(self):
        make("Milk later", due_date=date(2026, 10, 20))
        make("Milk done", due_date=date(2026, 10, 1), done=True)
        make("Call home", due_date=date(2026, 10, 5))
        make("Milk soon", due_date=date(2026, 10, 12))
        self.assertEqual(
            self.titles("/?show=active&q=milk&sort=due"), ["Milk soon", "Milk later"]
        )

    # Sort: protect what already works.

    def test_default_is_oldest_first(self):
        make("C")
        make("A")
        make("B")
        for url in ["/", "/?sort=created", "/?sort=banana"]:
            with self.subTest(url=url):
                self.assertEqual(self.titles(url), ["C", "A", "B"])

    def test_redirect_drops_a_bad_sort(self):
        todo = make("Buy milk")
        toggle = reverse("todo_toggle", args=[todo.pk])
        for query in [
            "?sort=banana",
            "?sort=created",
            "?sort=title%0D%0ALocation:%20https://evil.example",
        ]:
            with self.subTest(query=query):
                response = self.client.post(toggle + query)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/")
