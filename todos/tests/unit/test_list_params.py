from django.http import QueryDict
from django.test import SimpleTestCase

from todos.views import list_params, list_query


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
