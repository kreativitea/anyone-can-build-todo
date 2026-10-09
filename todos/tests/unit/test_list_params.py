from unittest.mock import patch

from django.http import QueryDict
from django.test import SimpleTestCase

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
