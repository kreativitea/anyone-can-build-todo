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
            filter_links({}),
            [
                {"label": "All", "url": "/", "current": True},
                {"label": "Active", "url": "/?show=active", "current": False},
                {"label": "Completed", "url": "/?show=completed", "current": False},
            ],
        )

    def test_filter_links_keep_other_params(self):
        with patch("todos.views.list_params", list_params_with_q):
            links = filter_links({"show": "active", "q": "milk"})
        self.assertEqual(
            links,
            [
                {"label": "All", "url": "/?q=milk", "current": False},
                {"label": "Active", "url": "/?show=active&q=milk", "current": True},
                {
                    "label": "Completed",
                    "url": "/?show=completed&q=milk",
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
            link["url"] for link in filter_links({"show": "active", "selected": "5"})
        ]
        self.assertEqual(
            urls,
            ["/?selected=5", "/?show=active&selected=5", "/?show=completed&selected=5"],
        )

    def test_select_base(self):
        self.assertEqual(views.select_base({}), "/?selected=")
        self.assertEqual(
            views.select_base({"show": "active", "selected": "5"}),
            "/?show=active&selected=",
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
