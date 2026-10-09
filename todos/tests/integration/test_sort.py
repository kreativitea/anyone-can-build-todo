from datetime import date, timedelta

from django.db import connection
from django.db.models import QuerySet
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from todos.models import Todo
from todos.tests.integration.helpers import (
    LoggedInTestCase,
    list_path,
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
    ("manual", "My order"),  # reorder (16): the last link
]
CURRENT = ' aria-current="true"'


def nav(chosen, selected=None, *, list_id):
    """The whole sort <nav> of the list `list_id`, with `chosen` marked.

    `selected` is the id of the selected to-do: every link keeps it, last.
    """
    links = ""
    for value, label in LINKS:
        params = [] if value == "created" else [f"sort={value}"]
        if selected is not None:
            params.append(f"selected={selected}")
        href = list_path(list_id) + ("?" + "&amp;".join(params) if params else "")
        mark = CURRENT if value == chosen else ""
        links += f'<a href="{href}"{mark}>{label}</a>'
    return NAV.format(links=links)


def make_earlier(todo, than):
    """Set `todo`'s date added to just before `than`'s.

    Then the id order and the date-added order disagree: a test that needs the
    date-added order cannot pass by the id order by chance.
    """
    than.refresh_from_db()
    earlier = than.created_at - timedelta(seconds=1)
    Todo.objects.filter(pk=todo.pk).update(created_at=earlier)


class SortTests(LoggedInTestCase):
    def make(self, title, **fields):
        return self.make_todo(title=title, **fields)

    def titles(self, url):
        """The titles on the page at `url`, in the order the page shows them."""
        return page_parts(self.client.get(url)).titles

    # Sort: new behaviour. In every order test, the to-do that should come
    # FIRST is made LAST, so the old order (oldest first) can never pass.

    def test_sort_by_due_date(self):
        self.make("No date")
        self.make("Later", due_date=date(2026, 10, 20))
        self.make("Soon", due_date=date(2026, 10, 12))
        self.assertEqual(
            self.titles(self.list_url(query="?sort=due")), ["Soon", "Later", "No date"]
        )

    def test_due_date_ties_go_high_priority_first(self):
        self.make("Low", due_date=date(2026, 10, 12), priority=LOW)
        self.make("High", due_date=date(2026, 10, 12), priority=HIGH)
        self.assertEqual(self.titles(self.list_url(query="?sort=due")), ["High", "Low"])

    def test_due_and_priority_ties_keep_date_added_order(self):
        b = self.make("B", due_date=date(2026, 10, 12))
        a = self.make("A", due_date=date(2026, 10, 12))
        make_earlier(a, than=b)  # id order: B, A. Date added: A, B.
        self.assertEqual(self.titles(self.list_url(query="?sort=due")), ["A", "B"])

    def test_sort_by_priority(self):
        self.make("Low", priority=LOW)
        self.make("Medium", priority=MEDIUM)
        self.make("High", priority=HIGH)
        self.assertEqual(
            self.titles(self.list_url(query="?sort=priority")),
            ["High", "Medium", "Low"],
        )

    def test_priority_ties_go_soonest_due_first(self):
        self.make("Low", priority=LOW)
        self.make("High no date", priority=HIGH)
        self.make("High later", priority=HIGH, due_date=date(2026, 10, 20))
        self.make("High soon", priority=HIGH, due_date=date(2026, 10, 12))
        self.assertEqual(
            self.titles(self.list_url(query="?sort=priority")),
            ["High soon", "High later", "High no date", "Low"],
        )

    def test_priority_and_due_ties_keep_date_added_order(self):
        b = self.make("B", priority=HIGH)
        a = self.make("A", priority=HIGH)
        make_earlier(a, than=b)  # id order: B, A. Date added: A, B.
        self.assertEqual(self.titles(self.list_url(query="?sort=priority")), ["A", "B"])

    def test_sort_by_title_ignores_case(self):
        self.make("cherry")
        self.make("Banana")
        self.make("apple")
        self.assertEqual(
            self.titles(self.list_url(query="?sort=title")),
            ["apple", "Banana", "cherry"],
        )

    def test_title_ties_keep_date_added_order(self):
        b = self.make("Buy milk")
        a = self.make("buy milk")
        make_earlier(a, than=b)  # id order: B, A. Date added: A, B.
        self.make("apple")
        self.assertEqual(
            self.titles(self.list_url(query="?sort=title")),
            ["apple", "buy milk", "Buy milk"],
        )

    def test_sort_by_title_hiragana(self):
        self.make("うどん")
        self.make("いちご")
        self.make("あめ")
        self.assertEqual(
            self.titles(self.list_url(query="?sort=title")),
            ["あめ", "いちご", "うどん"],
        )

    def test_sort_links_are_on_the_page(self):
        response = self.client.get(self.list_url())
        self.assertContains(
            response, nav("created", list_id=self.todo_list.pk), count=1, html=True
        )

    def test_chosen_sort_is_marked(self):
        for url, chosen in [
            (self.list_url(query="?sort=priority"), "priority"),
            (self.list_url(query="?sort=banana"), "created"),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(
                    response, nav(chosen, list_id=self.todo_list.pk), count=1, html=True
                )
                # The filter's mark is not changed: only All has "page".
                self.assertEqual(page_parts(response).current_links, ["All"])

    def test_sort_row_stays_when_the_pane_is_open(self):
        todo = self.make("Buy milk")
        response = self.client.get(
            self.list_url(query=f"?sort=priority&selected={todo.pk}")
        )
        self.assertEqual(page_parts(response).panes, ["Details"])
        self.assertContains(
            response,
            nav("priority", selected=todo.pk, list_id=self.todo_list.pk),
            count=1,
            html=True,
        )

    def test_pane_keeps_the_sort(self):
        todo = self.make("Buy milk")
        response = self.client.get(self.list_url(query=f"?sort=due&selected={todo.pk}"))
        todo.refresh_from_db()
        pane = pane_element(
            todo,
            created=show_date(timezone.localtime(todo.created_at)),
            close_url=self.list_url(query="?sort=due"),
            edit_url=f"/{todo.pk}/edit/?sort=due&selected={todo.pk}",
        )
        self.assertContains(response, pane, count=1, html=True)

    def test_edit_page_cancel_keeps_the_sort(self):
        todo = self.make("Buy milk")
        response = self.client.get(f"/{todo.pk}/edit/?show=active&sort=due")
        self.assertContains(
            response,
            f'<a href="{self.list_url()}?show=active&amp;sort=due">Cancel</a>',
            html=True,
        )

    def test_every_sort_is_one_list_query(self):
        self.make("Low", priority=LOW, due_date=date(2026, 10, 12))
        self.make("High", priority=HIGH)
        self.make("Medium", done=True)
        with CaptureQueriesContext(connection) as plain:
            self.client.get(self.list_url())
        for value, _label, _order in SORTS:
            with self.subTest(sort=value):
                with CaptureQueriesContext(connection) as sorted_page:
                    response = self.client.get(self.list_url(query=f"?sort={value}"))
                self.assertEqual(len(sorted_page), len(plain))
                # The database sorts. Sorting in Python (sorted()) costs no
                # extra query, but it turns the list into a Python list.
                self.assertIsInstance(response.context["todos"], QuerySet)

    def test_sort_is_kept_everywhere(self):
        todo = self.make("Buy milk")
        response = self.client.get(self.list_url(query="?show=active&q=milk&sort=due"))
        query = "?show=active&q=milk&sort=due"
        parts = [
            f'<a href="{self.list_url()}?show=active&amp;q=milk&amp;sort=due" '
            'aria-current="page">Active</a>',
            '<input type="hidden" name="sort" value="due">',
            f'<a href="{self.list_url()}?show=active&amp;sort=due">Clear search</a>',
            f'<a class="edit" href="/{todo.pk}/edit/?show=active&amp;q=milk&amp;'
            'sort=due" aria-label="Edit Buy milk">Edit</a>',
            f'<a href="{self.list_url()}?show=active&amp;q=milk&amp;sort=title">Title</a>',
            title_element(todo, query),
        ]
        for part in parts:
            with self.subTest(part=part):
                self.assertContains(response, part, count=1, html=True)

    def test_every_post_form_keeps_the_sort(self):
        active = self.make("Buy milk")
        self.make("Call home", done=True)
        query = "?show=active&sort=title"
        response = self.client.get(self.list_url() + query)
        self.assertEqual(
            page_parts(response).post_actions,
            [
                self.add_url() + query,
                reverse("todo_toggle", args=[active.pk]) + query,
                reverse("todo_delete", args=[active.pk]) + query,
                self.delete_completed_url() + query,
            ],
        )

    def test_post_goes_back_with_the_sort(self):
        query = "?show=active&sort=due"
        todo = self.make("Buy milk")
        other = self.make("Call home")
        cases = [
            ("toggle", reverse("todo_toggle", args=[todo.pk]), {"done": "1"}),
            ("delete", reverse("todo_delete", args=[other.pk]), {}),
            ("add", self.add_url(), {"title": "New"}),
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
                self.assertEqual(response["Location"], self.list_url() + query)

    def test_sort_filter_and_search_together(self):
        self.make("Milk later", due_date=date(2026, 10, 20))
        self.make("Milk done", due_date=date(2026, 10, 1), done=True)
        self.make("Call home", due_date=date(2026, 10, 5))
        self.make("Milk soon", due_date=date(2026, 10, 12))
        self.assertEqual(
            self.titles(self.list_url(query="?show=active&q=milk&sort=due")),
            ["Milk soon", "Milk later"],
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
            # Reorder (16): My order, by the number each to-do has.
            "manual": (
                [
                    ("Done first", {"done": True, "position": 1}),
                    ("Open late", {"position": 5}),
                    ("Open early", {"position": 2}),
                    ("Done later", {"done": True, "position": 3}),
                ],
                ["Open early", "Open late", "Done first", "Done later"],
            ),
        }
        # Every sort in the table has a case here.
        self.assertEqual(set(cases), {value for value, _label, _order in SORTS})
        for value, (todos, expected) in cases.items():
            with self.subTest(sort=value):
                Todo.objects.all().delete()
                for title, fields in todos:
                    self.make(title, **fields)
                self.assertEqual(
                    self.titles(self.list_url(query=f"?sort={value}")), expected
                )

    # Sort: protect what already works.

    def test_default_is_oldest_first(self):
        # id order: B, A, C. Date added: C, A, B.
        b = self.make("B")
        a = self.make("A")
        c = self.make("C")
        make_earlier(a, than=b)
        make_earlier(c, than=a)
        for url in [
            self.list_url(),
            self.list_url(query="?sort=created"),
            self.list_url(query="?sort=banana"),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.titles(url), ["C", "A", "B"])

    def test_redirect_drops_a_bad_sort(self):
        todo = self.make("Buy milk")
        toggle = reverse("todo_toggle", args=[todo.pk])
        for query in [
            "?sort=banana",
            "?sort=created",
            "?sort=title%0D%0ALocation:%20https://evil.example",
        ]:
            with self.subTest(query=query):
                response = self.client.post(toggle + query, {"done": "1"})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], self.list_url())
