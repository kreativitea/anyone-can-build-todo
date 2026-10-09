from urllib.parse import urlencode

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from todos.models import Todo
from todos.tests.integration.helpers import LoggedInTestCase, page_parts, title_element

# ギュウニュウ in normal katakana, written with code points so that no editor
# can change how its letters are stored.
GYUUNYUU = "ギュウニュウ"

# "می‌خواهم" (Persian), with a zero-width non-joiner (U+200C) inside.
PERSIAN = "می‌خواهم"
# 👩‍💻: a woman, a zero-width joiner (U+200D), and a laptop.
CODER = "\U0001f469‍\U0001f4bb"

# Note: on SQLite, `icontains` and `contains` cannot be told apart by a test
# (both ignore big and small letters for A to Z), so no test tries.

# The box's maxlength: the browser counts UTF-16 units, so it is 2 × 200.
BOX = '<input type="search" id="search-q" name="q" value="{}" maxlength="400">'

# The whole search form on a list page (`{list}`, its address): no hidden input
# and no "Clear search" link.
PLAIN_SEARCH_FORM = (
    '<form class="search" role="search" method="get" action="{list}">'
    '<label for="search-q">Search to-dos</label>'
    f"{BOX.format('')}"
    '<button type="submit">Search</button>'
    "</form>"
)


def search_box(value):
    """The search box, as the whole element, with `value` already escaped."""
    return BOX.format(value)


def query(**params):
    """The list query in the title links, like "?show=active&q=milk"."""
    return "?" + urlencode(params) if params else ""


class SearchTests(LoggedInTestCase):
    def make(self, *titles, **fields):
        """Make one of ana's to-dos per title, in order, and return them."""
        return [self.make_todo(title=title, **fields) for title in titles]

    def setUp(self):
        super().setUp()
        self.buy = self.make_todo(title="Buy milk")
        self.cow = self.make_todo(title="Milk the cow", done=True)
        self.call = self.make_todo(title="Call home")

    def search(self, q, **other):
        """Open the list with this search. The test client encodes the address."""
        return self.client.get(self.list_url(), {**other, "q": q})

    def assert_shown(self, response, shown, list_query="", hints=()):
        """Exactly the to-dos in `shown` are on the list, in order.

        `parts.titles` proves that no other to-do is shown. Each shown title
        is then compared as the whole element, with its link (which keeps
        `list_query`) and with the "matches in notes" hint only for `hints`.
        """
        self.assertEqual(page_parts(response).titles, [t.title for t in shown])
        for todo in shown:
            element = title_element(todo, list_query, match_hint=todo in hints)
            self.assertContains(response, element, count=1, html=True)

    # Search: new behaviour.

    def test_search_finds_part_of_the_title_in_any_case(self):
        for q in ["milk", "MILK", "Milk"]:
            with self.subTest(q=q):
                response = self.search(q)
                self.assert_shown(response, [self.buy, self.cow], query(q=q))

    def test_search_finds_japanese(self):
        Todo.objects.all().delete()
        milk, _ = self.make("牛乳を買う", "Call home")
        response = self.search("牛乳")
        self.assert_shown(response, [milk], query(q="牛乳"))

    def test_wide_letters_find_normal_letters(self):
        Todo.objects.all().delete()
        buy, gyuunyuu, _ = self.make("Buy milk", GYUUNYUU, "Call home")
        cases = [
            ("ｍｉｌｋ", buy),
            ("ＭＩＬＫ", buy),
            ("ｷﾞｭｳﾆｭｳ", gyuunyuu),  # half-width katakana
        ]
        for q, found in cases:
            with self.subTest(q=q):
                response = self.search(q)
                self.assert_shown(response, [found], query(q=q))

    def test_typed_wide_letters_find_a_wide_title(self):
        Todo.objects.all().delete()
        tea, buy, _ = self.make("ＭＩＬＫ tea", "Buy milk", "Call home")
        response = self.search("ＭＩＬＫ")
        self.assert_shown(response, [tea, buy], query(q="ＭＩＬＫ"))

    def test_search_treats_wildcards_as_text(self):
        Todo.objects.all().delete()
        done, underscore, _, _ = self.make(
            "100% done", "file_name", "file-name", "Call home"
        )
        # `file-name` matters: an unescaped `_` would match its `-`.
        cases = [("%", done), ("_", underscore), ("file_name", underscore)]
        for q, found in cases:
            with self.subTest(q=q):
                response = self.search(q)
                self.assert_shown(response, [found], query(q=q))

    def test_search_keeps_the_joiners(self):
        Todo.objects.all().delete()
        persian, coder, _ = self.make(PERSIAN, f"{CODER} review", "Call home")
        for q, found in [(PERSIAN, persian), (CODER, coder)]:
            with self.subTest(q=q):
                response = self.search(q)
                self.assert_shown(response, [found], query(q=q))

    def test_search_finds_words_only_in_the_notes(self):
        Todo.objects.all().delete()
        shopping = self.make_todo(title="Shopping", notes="milk and eggs")
        self.make_todo(title="Call home")
        response = self.search("MILK")
        self.assert_shown(response, [shopping], query(q="MILK"), hints=[shopping])

    def test_wide_letters_find_words_in_the_notes(self):
        Todo.objects.all().delete()
        shopping = self.make_todo(title="Shopping", notes="milk and eggs")
        self.make_todo(title="Call home")
        response = self.search("ｍｉｌｋ")
        self.assert_shown(response, [shopping], query(q="ｍｉｌｋ"), hints=[shopping])

    def test_notes_only_match_shows_a_hint(self):
        # Buy milk matches in the title (and its notes): no hint.
        # Shopping matches only in its notes: the hint.
        self.buy.notes = "the milk in the blue box"
        self.buy.save()
        shopping = self.make_todo(title="Shopping", notes="milk and eggs")
        # "Milk the cow" is completed, so it comes last (completed go last).
        with self.subTest("a search"):
            response = self.search("milk")
            self.assert_shown(
                response, [self.buy, shopping, self.cow], query(q="milk"), [shopping]
            )
        with self.subTest("no search: never a hint"):
            response = self.client.get(self.list_url())
            self.assert_shown(response, [self.buy, self.call, shopping, self.cow])

    def test_no_match_message_shows_the_cleaned_word(self):
        # Spaces and a zero-width space around the word are cleaned away.
        response = self.search(" banana​ ")
        self.assertContains(
            response, '<li>No to-dos match "banana".</li>', count=1, html=True
        )

    def test_page_title_names_the_search(self):
        cases = [
            # Lists (13): the title names the open list too.
            ({}, "<title>My to-dos – To-do list</title>"),
            ({"q": "milk"}, "<title>Search: milk – My to-dos – To-do list</title>"),
            (
                {"q": "<b>hi</b>"},
                "<title>Search: &lt;b&gt;hi&lt;/b&gt; – My to-dos – To-do list</title>",
            ),
        ]
        for params, page_title in cases:
            with self.subTest(params=params):
                response = self.client.get(self.list_url(), params)
                self.assertContains(response, page_title, count=1, html=True)

    def test_search_form_on_the_plain_list(self):
        response = self.client.get(self.list_url())
        self.assertContains(
            response, PLAIN_SEARCH_FORM.format(list=self.list_url()), count=1, html=True
        )

    def test_search_form_with_a_filter_and_a_word(self):
        response = self.client.get(self.list_url(query="?show=active&q=milk"))
        form = (
            f'<form class="search" role="search" method="get" action="{self.list_url()}">'
            '<input type="hidden" name="show" value="active">'
            '<label for="search-q">Search to-dos</label>'
            f"{search_box('milk')}"
            '<button type="submit">Search</button>'
            f'<a href="{self.list_url()}?show=active">Clear search</a>'
            "</form>"
        )
        self.assertContains(response, form, count=1, html=True)

    def test_search_form_keeps_the_selected_todo(self):
        pk = self.buy.pk
        response = self.client.get(self.list_url(query=f"?q=milk&selected={pk}"))
        form = (
            f'<form class="search" role="search" method="get" action="{self.list_url()}">'
            f'<input type="hidden" name="selected" value="{pk}">'
            '<label for="search-q">Search to-dos</label>'
            f"{search_box('milk')}"
            '<button type="submit">Search</button>'
            f'<a href="{self.list_url()}?selected={pk}">Clear search</a>'
            "</form>"
        )
        self.assertContains(response, form, count=1, html=True)

    def test_empty_search_is_the_same_as_no_search(self):
        for url in [
            self.list_url(query="?q="),
            self.list_url(query="?q=%20%20"),
            self.list_url(query="?q=%E3%80%80"),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                # "Milk the cow" is completed, so it comes last.
                self.assert_shown(response, [self.buy, self.call, self.cow])
                self.assertContains(
                    response,
                    PLAIN_SEARCH_FORM.format(list=self.list_url()),
                    count=1,
                    html=True,
                )
                self.assertContains(
                    response,
                    f'<a href="{self.list_url()}" aria-current="page">All</a>',
                    html=True,
                )

    def test_search_word_is_escaped(self):
        response = self.search('"><script>alert(1)</script>')
        escaped = "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
        self.assertContains(response, search_box(escaped), count=1, html=True)
        self.assertContains(
            response, f'<li>No to-dos match "{escaped}".</li>', count=1, html=True
        )
        # The one page-wide check, on purpose: the raw text is nowhere.
        self.assertNotIn("<script>alert(1)", response.content.decode())

    def test_no_match_message_for_each_filter(self):
        cases = [
            ({}, '<li>No to-dos match "banana".</li>'),
            ({"show": "active"}, '<li>No active to-dos match "banana".</li>'),
            ({"show": "completed"}, '<li>No completed to-dos match "banana".</li>'),
        ]
        for other, message in cases:
            with self.subTest(other=other):
                response = self.search("banana", **other)
                self.assertContains(response, message, count=1, html=True)

    def test_search_and_filter_together(self):
        response = self.client.get(self.list_url(query="?show=active&q=milk"))
        self.assert_shown(response, [self.buy], query(show="active", q="milk"))

    def test_filter_links_keep_the_search(self):
        response = self.client.get(self.list_url(query="?q=milk"))
        for link in [
            f'<a href="{self.list_url()}?q=milk" aria-current="page">All</a>',
            f'<a href="{self.list_url()}?show=active&amp;q=milk">Active</a>',
            f'<a href="{self.list_url()}?show=completed&amp;q=milk">Completed</a>',
        ]:
            with self.subTest(link=link):
                self.assertContains(response, link, count=1, html=True)

    def test_every_post_form_keeps_the_search(self):
        # On /?q=milk, "Milk the cow" (completed) is shown too, with its forms.
        for list_query in ["?show=active&q=milk", "?q=milk"]:
            with self.subTest(query=list_query):
                actions = page_parts(
                    self.client.get(self.list_url() + list_query)
                ).post_actions
                self.assertGreaterEqual(len(actions), 3)
                for action in actions:
                    path, mark, rest = action.partition("?")
                    self.assertEqual(mark + rest, list_query, action)

    def test_edit_link_keeps_the_search(self):
        response = self.client.get(self.list_url(query="?q=milk"))
        link = (
            f'<a class="edit" href="/{self.buy.pk}/edit/?q=milk" '
            'aria-label="Edit Buy milk">Edit</a>'
        )
        self.assertContains(response, link, count=1, html=True)

    def test_edit_page_keeps_the_search(self):
        list_query = "?show=active&q=milk"
        response = self.client.get(f"/{self.buy.pk}/edit/{list_query}")
        self.assertEqual(
            page_parts(response).post_actions, [f"/{self.buy.pk}/edit/{list_query}"]
        )
        self.assertContains(
            response,
            f'<a href="{self.list_url()}?show=active&amp;q=milk">Cancel</a>',
            html=True,
        )

    def test_actions_go_back_to_the_search(self):
        def post(name, args, params, data=None):
            url = reverse(name, args=args) + "?" + urlencode(params)
            return self.client.post(url, data or {})

        extra = self.make_todo(title="Milk to delete")
        toggle = ("todo_toggle", [self.buy.pk])
        done = {"done": "1"}
        cases = [
            (
                (
                    "todo_add",
                    [self.todo_list.pk],
                    {"q": "milk"},
                    {"title": "Milk again"},
                ),
                self.list_url(query="?q=milk"),
            ),
            ((*toggle, {"q": "milk"}, done), self.list_url(query="?q=milk")),
            (
                ("todo_delete", [extra.pk], {"show": "active", "q": "milk"}),
                self.list_url(query="?show=active&q=milk"),
            ),
            (
                (*toggle, {"q": "牛乳"}, done),
                self.list_url(query="?q=%E7%89%9B%E4%B9%B3"),
            ),
            ((*toggle, {"q": "buy milk"}, done), self.list_url(query="?q=buy+milk")),
            # The `&` stays inside q: it never becomes a second parameter.
            (
                (*toggle, {"q": "a&next=https://evil.example"}, done),
                self.list_url(query="?q=a%26next%3Dhttps%3A%2F%2Fevil.example"),
            ),
            (
                ("todo_edit", [self.buy.pk], {"q": "milk"}, {"title": "Buy oat milk"}),
                self.list_url(query="?q=milk"),
            ),
            (
                (
                    "todo_delete_completed",
                    [self.todo_list.pk],
                    {"q": "milk"},
                    {"ids": [self.cow.pk]},
                ),
                self.list_url(query="?q=milk"),
            ),
        ]
        for args, location in cases:
            with self.subTest(name=args[0], params=args[2]):
                response = post(*args)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], location)

    def test_add_error_keeps_the_search(self):
        response = self.client.post(
            self.add_url() + "?q=milk", {"title": "New", "due_date": "not-a-date"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid date.")
        self.assert_shown(response, [self.buy, self.cow], query(q="milk"))
        self.assertContains(response, search_box("milk"), count=1, html=True)

    # Search with the details pane (21).

    def test_search_that_hides_the_selected_todo_closes_the_pane(self):
        # Call home is selected, but the search for milk hides it: the page is
        # exactly the page without the selection.
        hidden = self.list_url(query=f"?q=milk&selected={self.call.pk}")
        response = self.client.get(hidden)
        self.assertEqual(page_parts(response).panes, [])
        self.assertEqual(page_parts(response).selected_titles, [])
        self.assertContains(
            response,
            f"<a href='{self.list_url()}'>Clear search</a>",
            count=1,
            html=True,
        )

    def test_a_selected_result_opens_the_pane(self):
        response = self.client.get(
            self.list_url(query=f"?q=milk&selected={self.buy.pk}")
        )
        parts = page_parts(response)
        self.assertEqual(parts.panes, ["Details"])
        self.assertEqual(parts.selected_titles, ["Buy milk"])

    # Search: protect what already works.

    def test_search_changes_nothing(self):
        def rows():
            return list(Todo.objects.order_by("pk").values_list("pk", "done"))

        before = rows()
        self.search("milk")
        self.assertEqual(rows(), before)

    def test_search_costs_no_extra_query(self):
        # The hint comes from the same query as the list (an annotation).
        self.make_todo(title="Shopping", notes="milk and eggs")
        with CaptureQueriesContext(connection) as without:
            self.client.get(self.list_url())
        with CaptureQueriesContext(connection) as with_search:
            self.search("milk")
        self.assertEqual(len(with_search), len(without))

    def test_count_and_footer_ignore_the_search(self):
        # The whole table has 2 active to-dos: Buy milk and Call home.
        for q in ["milk", "banana"]:
            with self.subTest(q=q):
                response = self.search(q)
                self.assertContains(
                    response, '<p class="count">2 items left</p>', count=1, html=True
                )

    def test_delete_completed_ignores_the_search(self):
        Todo.objects.all().delete()
        buy, call = self.make("Buy milk", "Call home", done=True)
        response = self.search("banana")
        # The button and the ids only: the form's address is checked by
        # test_every_post_form_keeps_the_search.
        self.assertContains(
            response,
            '<button type="submit">Delete 2 completed to-dos</button>',
            count=1,
            html=True,
        )
        for pk in [buy.pk, call.pk]:
            self.assertContains(
                response,
                f'<input type="hidden" name="ids" value="{pk}">',
                count=1,
                html=True,
            )
