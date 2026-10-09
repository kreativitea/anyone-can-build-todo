from unittest.mock import patch

from django.http import QueryDict
from django.test import SimpleTestCase

from todos import views
from todos.views import filter_links, list_params, list_query


class ListParamsTests(SimpleTestCase):
    def test_list_params_keeps_known_values(self):
        cases = [
            ("show=active", {"show": "active"}),
            ("show=completed", {"show": "completed"}),
            ("show=active&next=https://evil.example", {"show": "active"}),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(list_params(QueryDict(query)), expected)

    def test_list_params_drops_the_rest(self):
        for query in [
            "",
            "show=all",
            "show=",
            "show=COMPLETED",
            "show=done",
            "show=banana",
            "show=https://evil.example",
            "show=completed%0D%0A",  # a line break after the value
            "show=completed%26next%3Dx",  # a hidden "&next=x" inside the value
            "next=https://evil.example",
        ]:
            with self.subTest(query=query):
                self.assertEqual(list_params(QueryDict(query)), {})

    def test_list_query(self):
        self.assertEqual(list_query({}), "")
        self.assertEqual(list_query({"show": "active"}), "?show=active")


# The list in the addresses below (lists, 13): the links are for /lists/1/.
LIST_ID = 1


def list_params_with_q(data):
    """A stub: list_params, plus a pretend search parameter `q`.

    Search (feature 10) will add a parameter like this. The stub shows that the
    filter links keep it, without waiting for search to exist.
    """
    params = list_params(data)
    if data.get("q"):
        params["q"] = data["q"]
    return params


class FilterLinksTests(SimpleTestCase):
    def test_filter_links_with_no_params(self):
        self.assertEqual(
            filter_links({}, LIST_ID),
            [
                {"label": "All", "url": "/lists/1/", "current": True},
                {"label": "Active", "url": "/lists/1/?show=active", "current": False},
                {
                    "label": "Completed",
                    "url": "/lists/1/?show=completed",
                    "current": False,
                },
            ],
        )

    def test_filter_links_keep_other_params(self):
        with patch("todos.views.list_params", list_params_with_q):
            links = filter_links({"show": "active", "q": "milk"}, LIST_ID)
        self.assertEqual(
            links,
            [
                {"label": "All", "url": "/lists/1/?q=milk", "current": False},
                {
                    "label": "Active",
                    "url": "/lists/1/?show=active&q=milk",
                    "current": True,
                },
                {
                    "label": "Completed",
                    "url": "/lists/1/?show=completed&q=milk",
                    "current": False,
                },
            ],
        )


class SelectedTests(SimpleTestCase):
    """The details pane (feature 21): ?selected=<id> is a list parameter."""

    # Details pane: new behaviour.

    def test_list_params_keeps_a_good_selected(self):
        cases = [
            ("selected=5", {"selected": "5"}),
            ("selected=007", {"selected": "7"}),  # one address per to-do
            ("selected=" + "9" * 18, {"selected": "9" * 18}),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(list_params(QueryDict(query)), expected)

    def test_selected_is_the_last_key(self):
        result = list_params(QueryDict("selected=5&show=active"))
        self.assertEqual(result, {"show": "active", "selected": "5"})
        self.assertEqual(list(result), ["show", "selected"])

    def test_filter_links_keep_selected(self):
        urls = [
            link["url"]
            for link in filter_links({"show": "active", "selected": "5"}, LIST_ID)
        ]
        self.assertEqual(
            urls,
            [
                "/lists/1/?selected=5",
                "/lists/1/?show=active&selected=5",
                "/lists/1/?show=completed&selected=5",
            ],
        )

    def test_select_base(self):
        self.assertEqual(views.select_base({}, LIST_ID), "/lists/1/?selected=")
        self.assertEqual(
            views.select_base({"show": "active", "selected": "5"}, LIST_ID),
            "/lists/1/?show=active&selected=",
        )

    # Details pane: protect what already works.

    def test_list_params_drops_a_bad_selected(self):
        for query in [
            "selected=",
            "selected=abc",
            "selected=-1",
            "selected=1.5",
            "selected=1e3",
            "selected=%EF%BC%95",  # a wide 5: isdigit() says yes
            "selected=%C2%B2",  # a superscript 2: isdigit() says yes, int() crashes
            "selected=5%C2%B2",  # "5²"
            "selected=" + "9" * 19,  # may not fit in SQLite's integer
            "selected=5%26next%3Dx",  # a hidden "&next=x" inside the value
        ]:
            with self.subTest(query=query):
                self.assertEqual(list_params(QueryDict(query)), {})


# Search (feature 10): `q` in the address. Each row is a query string, and the
# search word that list_params must keep from it.
KEEPS_THE_SEARCH = [
    ("q=milk", "milk"),
    ("q=Buy+milk", "Buy milk"),
    ("q=%E7%89%9B%E4%B9%B3", "牛乳"),
    # Cleaning is not escaping: the template escapes.
    ("q=%3Cscript%3E", "<script>"),
    # Wide letters are kept as typed. NFKC is done only inside the search.
    ("q=%EF%BD%8D%EF%BD%89%EF%BD%8C%EF%BD%8B", "ｍｉｌｋ"),
    # The two joiners are kept: Persian, Hindi and emoji need them.
    # "می‌خواهم" (Persian) has a zero-width non-joiner (U+200C).
    (
        "q=%D9%85%DB%8C%E2%80%8C%D8%AE%D9%88%D8%A7%D9%87%D9%85",
        "می‌خواهم",
    ),
    # 👩‍💻 is a woman, a zero-width joiner (U+200D), and a laptop.
    ("q=%F0%9F%91%A9%E2%80%8D%F0%9F%92%BB", "\U0001f469‍\U0001f4bb"),
]
WHITE_SPACE = [
    ("q=%20%20milk%20", "milk"),
    ("q=buy%20%20%20milk", "buy milk"),
    ("q=buy%09milk", "buy milk"),  # a tab
    ("q=milk%0D%0A", "milk"),  # a line break
    ("q=buy%E3%80%80milk", "buy milk"),  # a wide (Japanese) space
]
INVISIBLE = [
    ("q=mi%00lk", "milk"),  # the "null" character
    ("q=mi%07lk", "milk"),  # the bell
    ("q=mi%E2%80%8Blk", "milk"),  # a zero-width space
    ("q=mi%C2%ADlk", "milk"),  # a soft hyphen
]
LONG = [
    ("q=" + "a" * 250, "a" * 200),
    # The cut ends on a space, which is removed.
    ("q=" + "a" * 199 + "%20b", "a" * 199),
    # Clean first, then cut: invisible characters do not use up the 200.
    ("q=" + "%E2%80%8B" * 10 + "a" * 200, "a" * 200),
]
EMPTY_SEARCHES = [
    "q=",
    "q=%20%20",
    "q=%E3%80%80",
    "q=%00",
    "q=%E2%80%8B",
    "q=%0D%0A",
    "",  # no q at all
]


class SearchParamsTests(SimpleTestCase):
    def check_search(self, cases):
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(list_params(QueryDict(query)), {"q": expected})

    # Search: new behaviour.

    def test_list_params_keeps_the_search(self):
        self.check_search(KEEPS_THE_SEARCH)

    def test_list_params_makes_white_space_one_space(self):
        self.check_search(WHITE_SPACE)

    def test_list_params_removes_invisible_characters(self):
        self.check_search(INVISIBLE)

    def test_list_params_cuts_a_long_search(self):
        self.check_search(LONG)

    def test_list_params_keeps_search_and_filter_in_order(self):
        result = list_params(QueryDict("q=milk&show=active"))
        self.assertEqual(result, {"show": "active", "q": "milk"})
        self.assertEqual(list(result), ["show", "q"])

    def test_selected_stays_after_the_search(self):
        result = list_params(QueryDict("selected=5&q=milk&show=active"))
        self.assertEqual(list(result), ["show", "q", "selected"])

    # Search: protect what already works.

    def test_list_params_drops_an_empty_search(self):
        for query in EMPTY_SEARCHES:
            with self.subTest(query=query):
                self.assertEqual(list_params(QueryDict(query)), {})

    def test_list_params_twice_is_the_same(self):
        rows = KEEPS_THE_SEARCH + WHITE_SPACE + INVISIBLE + LONG
        queries = [query for query, _ in rows]
        queries += EMPTY_SEARCHES + ["q=milk&show=active"]
        # Sort (9): sort_links and filter_links call list_params again.
        queries += ["sort=due", "show=active&q=milk&sort=title"]
        for query in queries:
            with self.subTest(query=query):
                once = list_params(QueryDict(query))
                self.assertEqual(list_params(once), once)

    def test_list_query_with_search(self):
        cases = [
            ({"q": "buy milk"}, "?q=buy+milk"),
            ({"show": "active", "q": "milk"}, "?show=active&q=milk"),
            ({"q": "牛乳"}, "?q=%E7%89%9B%E4%B9%B3"),
            ({"q": "a&next=x"}, "?q=a%26next%3Dx"),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                self.assertEqual(list_query(params), expected)


class SortParamsTests(SimpleTestCase):
    """Sort (feature 9): ?sort=<value> is a list parameter."""

    # Sort: new behaviour.

    def test_list_params_keeps_the_sort(self):
        for value in ["due", "priority", "title"]:
            with self.subTest(sort=value):
                self.assertEqual(
                    list_params(QueryDict(f"sort={value}")), {"sort": value}
                )

    def test_list_params_order_is_show_q_sort(self):
        result = list_params(QueryDict("sort=due&q=milk&show=active"))
        self.assertEqual(list(result), ["show", "q", "sort"])

    def test_selected_stays_after_the_sort(self):
        result = list_params(QueryDict("selected=5&sort=due&show=active"))
        self.assertEqual(list(result), ["show", "sort", "selected"])

    def test_sort_links(self):
        # Imported here, so only this test fails while sort_links is missing.
        from todos.views import sort_links

        self.assertEqual(
            sort_links({"show": "active"}, LIST_ID),
            [
                {
                    "label": "Date added",
                    "url": "/lists/1/?show=active",
                    "current": True,
                },
                {
                    "label": "Due date",
                    "url": "/lists/1/?show=active&sort=due",
                    "current": False,
                },
                {
                    "label": "Priority",
                    "url": "/lists/1/?show=active&sort=priority",
                    "current": False,
                },
                {
                    "label": "Title",
                    "url": "/lists/1/?show=active&sort=title",
                    "current": False,
                },
            ],
        )
        chosen = [
            link["label"]
            for link in sort_links({"sort": "title"}, LIST_ID)
            if link["current"]
        ]
        self.assertEqual(chosen, ["Title"])
        # The selection stays, and stays last.
        self.assertEqual(
            [link["url"] for link in sort_links({"selected": "5"}, LIST_ID)],
            [
                "/lists/1/?selected=5",
                "/lists/1/?sort=due&selected=5",
                "/lists/1/?sort=priority&selected=5",
                "/lists/1/?sort=title&selected=5",
            ],
        )

    # Sort: protect what already works.

    def test_list_params_drops_the_default_and_unknown_sorts(self):
        for query in [
            "sort=created",
            "sort=",
            "sort=banana",
            "sort=TITLE",
            "sort=-title",
            "sort=title%0D%0A",  # a line break after the value
            "sort=title%26next%3Dx",  # a hidden "&next=x" inside the value
            "",  # no sort at all
        ]:
            with self.subTest(query=query):
                self.assertEqual(list_params(QueryDict(query)), {})
