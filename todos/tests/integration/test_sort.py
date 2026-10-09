from datetime import date, timedelta

from django.db import connection
from django.db.models import QuerySet
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from todos.models import Todo
from todos.tests.integration.helpers import (
    page_parts,
    pane_element,
    show_date,
    title_element,
)
from todos.views import SORTS

HIGH = Todo.Priority.HIGH
MEDIUM = Todo.Priority.MEDIUM
LOW = Todo.Priority.LOW

# The sort links, as the whole <nav> element. The visible "Sort by:" is also
# the nav's name (aria-labelledby), so a screen reader says it once.
NAV = (
    '<nav class="sort" aria-labelledby="sort-label">'
    '<span id="sort-label">Sort by:</span>'
    "{links}"
    "</nav>"
)
LINKS = [
    ("created", "Date added"),
    ("due", "Due date"),
    ("priority", "Priority"),
    ("title", "Title"),
]
CURRENT = ' aria-current="true"'


def nav(chosen, selected=None):
    """The whole sort <nav>, with `chosen` marked.

    `selected` is the id of the selected to-do: every link keeps it, last.
    """
    links = ""
    for value, label in LINKS:
        params = [] if value == "created" else [f"sort={value}"]
        if selected is not None:
            params.append(f"selected={selected}")
        href = "/" + ("?" + "&amp;".join(params) if params else "")
        mark = CURRENT if value == chosen else ""
        links += f'<a href="{href}"{mark}>{label}</a>'
    return NAV.format(links=links)


def make(title, **fields):
    return Todo.objects.create(title=title, **fields)


def make_earlier(todo, than):
    """Set `todo`'s date added to just before `than`'s.

    Then the id order and the date-added order disagree: a test that needs the
    date-added order cannot pass by the id order by chance.
    """
    than.refresh_from_db()
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

    def test_due_and_priority_ties_keep_date_added_order(self):
        b = make("B", due_date=date(2026, 10, 12))
        a = make("A", due_date=date(2026, 10, 12))
        make_earlier(a, than=b)  # id order: B, A. Date added: A, B.
        self.assertEqual(self.titles("/?sort=due"), ["A", "B"])

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

    def test_priority_and_due_ties_keep_date_added_order(self):
        b = make("B", priority=HIGH)
        a = make("A", priority=HIGH)
        make_earlier(a, than=b)  # id order: B, A. Date added: A, B.
        self.assertEqual(self.titles("/?sort=priority"), ["A", "B"])

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

    def test_sort_row_stays_when_the_pane_is_open(self):
        todo = make("Buy milk")
        response = self.client.get(f"/?sort=priority&selected={todo.pk}")
        self.assertEqual(page_parts(response).panes, ["Details"])
        self.assertContains(
            response, nav("priority", selected=todo.pk), count=1, html=True
        )

    def test_pane_keeps_the_sort(self):
        todo = make("Buy milk")
        response = self.client.get(f"/?sort=due&selected={todo.pk}")
        todo.refresh_from_db()
        pane = pane_element(
            todo,
            created=show_date(timezone.localtime(todo.created_at)),
            close_url="/?sort=due",
            edit_url=f"/{todo.pk}/edit/?sort=due&selected={todo.pk}",
        )
        self.assertContains(response, pane, count=1, html=True)

    def test_edit_page_cancel_keeps_the_sort(self):
        todo = make("Buy milk")
        response = self.client.get(f"/{todo.pk}/edit/?show=active&sort=due")
        self.assertContains(
            response, '<a href="/?show=active&amp;sort=due">Cancel</a>', html=True
        )

    def test_every_sort_is_one_list_query(self):
        make("Low", priority=LOW, due_date=date(2026, 10, 12))
        make("High", priority=HIGH)
        make("Medium", done=True)
        with CaptureQueriesContext(connection) as plain:
            self.client.get("/")
        for value, _label, _order in SORTS:
            with self.subTest(sort=value):
                with CaptureQueriesContext(connection) as sorted_page:
                    response = self.client.get(f"/?sort={value}")
                self.assertEqual(len(sorted_page), len(plain))
                # The database sorts. Sorting in Python (sorted()) costs no
                # extra query, but it turns the list into a Python list.
                self.assertIsInstance(response.context["todos"], QuerySet)

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
            ("toggle", reverse("todo_toggle", args=[todo.pk]), {"done": "1"}),
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

    def test_completed_go_last_in_every_sort(self):
        # Owner decision: in every sort, open to-dos first, then completed ones,
        # each part in that sort's order. In each case a completed to-do would
        # come FIRST without the rule: added first, due soonest, High, or "A".
        cases = {
            "created": (
                [
                    ("Done first", {"done": True}),
                    ("Open A", {}),
                    ("Open B", {}),
                    ("Done last", {"done": True}),
                ],
                ["Open A", "Open B", "Done first", "Done last"],
            ),
            "due": (
                [
                    ("Done soon", {"done": True, "due_date": date(2026, 10, 1)}),
                    ("Open later", {"due_date": date(2026, 10, 20)}),
                    ("Open soon", {"due_date": date(2026, 10, 12)}),
                    ("Done no date", {"done": True}),
                    ("Open no date", {}),
                ],
                [
                    "Open soon",
                    "Open later",
                    "Open no date",
                    "Done soon",
                    "Done no date",
                ],
            ),
            "priority": (
                [
                    ("Done high", {"done": True, "priority": HIGH}),
                    ("Open low", {"priority": LOW}),
                    ("Open high", {"priority": HIGH}),
                    ("Done low", {"done": True, "priority": LOW}),
                ],
                ["Open high", "Open low", "Done high", "Done low"],
            ),
            "title": (
                [
                    ("A done", {"done": True}),
                    ("c open", {}),
                    ("B open", {}),
                    ("d done", {"done": True}),
                ],
                ["B open", "c open", "A done", "d done"],
            ),
        }
        # Every sort in the table has a case here.
        self.assertEqual(set(cases), {value for value, _label, _order in SORTS})
        for value, (todos, expected) in cases.items():
            with self.subTest(sort=value):
                Todo.objects.all().delete()
                for title, fields in todos:
                    make(title, **fields)
                self.assertEqual(self.titles(f"/?sort={value}"), expected)

    # Sort: protect what already works.

    def test_default_is_oldest_first(self):
        # id order: B, A, C. Date added: C, A, B.
        b = make("B")
        a = make("A")
        c = make("C")
        make_earlier(a, than=b)
        make_earlier(c, than=a)
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
                response = self.client.post(toggle + query, {"done": "1"})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/")
