from urllib.parse import urlencode

from django.test import TestCase
from django.urls import reverse

from todos.models import Todo
from todos.tests.integration.helpers import page_parts

# ギュウニュウ in normal katakana, written with code points so that no editor
# can change how its letters are stored.
GYUUNYUU = "ギュウニュウ"

# The whole search form on `/`: no hidden input and no "Clear search" link.
PLAIN_SEARCH_FORM = (
    '<form class="search" role="search" method="get" action="/">'
    '<label for="search-q">Search to-dos</label>'
    '<input type="search" id="search-q" name="q" value="" maxlength="200">'
    '<button type="submit">Search</button>'
    "</form>"
)


def title(text):
    """The title of a to-do on the list, as the whole element."""
    return f'<span class="title">{text}</span>'


def search_box(value):
    """The search box, as the whole element, with `value` already escaped."""
    return (
        f'<input type="search" id="search-q" name="q" value="{value}" maxlength="200">'
    )


class SearchTests(TestCase):
    def setUp(self):
        self.buy = Todo.objects.create(title="Buy milk")
        self.cow = Todo.objects.create(title="Milk the cow", done=True)
        self.call = Todo.objects.create(title="Call home")

    def search(self, q, **other):
        """Open the list with this search. The test client encodes the address."""
        return self.client.get("/", {**other, "q": q})

    def assert_shown(self, response, shown, hidden):
        """Each title in `shown` is on the page once; each in `hidden` is not."""
        for text in shown:
            self.assertContains(response, title(text), count=1, html=True)
        for text in hidden:
            self.assertContains(response, title(text), count=0, html=True)

    # Search: new behaviour.

    def test_search_finds_part_of_the_title_in_any_case(self):
        for q in ["milk", "MILK", "Milk"]:
            with self.subTest(q=q):
                response = self.search(q)
                self.assert_shown(response, ["Buy milk", "Milk the cow"], ["Call home"])

    def test_search_finds_japanese(self):
        Todo.objects.all().delete()
        Todo.objects.create(title="牛乳を買う")
        Todo.objects.create(title="Call home")
        response = self.search("牛乳")
        self.assert_shown(response, ["牛乳を買う"], ["Call home"])

    def test_wide_letters_find_normal_letters(self):
        Todo.objects.all().delete()
        titles = ["Buy milk", GYUUNYUU, "Call home"]
        for text in titles:
            Todo.objects.create(title=text)
        cases = [
            ("ｍｉｌｋ", "Buy milk"),
            ("ＭＩＬＫ", "Buy milk"),
            ("ｷﾞｭｳﾆｭｳ", GYUUNYUU),  # half-width katakana
        ]
        for q, found in cases:
            with self.subTest(q=q):
                response = self.search(q)
                others = [text for text in titles if text != found]
                self.assert_shown(response, [found], others)

    def test_typed_wide_letters_find_a_wide_title(self):
        Todo.objects.all().delete()
        for text in ["ＭＩＬＫ tea", "Buy milk", "Call home"]:
            Todo.objects.create(title=text)
        response = self.search("ＭＩＬＫ")
        self.assert_shown(response, ["ＭＩＬＫ tea", "Buy milk"], ["Call home"])

    def test_search_treats_wildcards_as_text(self):
        Todo.objects.all().delete()
        titles = ["100% done", "file_name", "file-name", "Call home"]
        for text in titles:
            Todo.objects.create(title=text)
        # `file-name` matters: an unescaped `_` would match its `-`.
        cases = [("%", "100% done"), ("_", "file_name"), ("file_name", "file_name")]
        for q, found in cases:
            with self.subTest(q=q):
                response = self.search(q)
                others = [text for text in titles if text != found]
                self.assert_shown(response, [found], others)

    def test_search_form_on_the_plain_list(self):
        response = self.client.get("/")
        self.assertContains(response, PLAIN_SEARCH_FORM, count=1, html=True)

    def test_search_form_with_a_filter_and_a_word(self):
        response = self.client.get("/?show=active&q=milk")
        form = (
            '<form class="search" role="search" method="get" action="/">'
            '<input type="hidden" name="show" value="active">'
            '<label for="search-q">Search to-dos</label>'
            f"{search_box('milk')}"
            '<button type="submit">Search</button>'
            '<a href="/?show=active">Clear search</a>'
            "</form>"
        )
        self.assertContains(response, form, count=1, html=True)

    def test_empty_search_is_the_same_as_no_search(self):
        for url in ["/?q=", "/?q=%20%20", "/?q=%E3%80%80"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_shown(
                    response, ["Buy milk", "Milk the cow", "Call home"], []
                )
                self.assertContains(response, PLAIN_SEARCH_FORM, count=1, html=True)
                self.assertContains(
                    response, '<a href="/" aria-current="page">All</a>', html=True
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
        response = self.client.get("/?show=active&q=milk")
        self.assert_shown(response, ["Buy milk"], ["Milk the cow", "Call home"])

    def test_filter_links_keep_the_search(self):
        response = self.client.get("/?q=milk")
        for link in [
            '<a href="/?q=milk" aria-current="page">All</a>',
            '<a href="/?show=active&amp;q=milk">Active</a>',
            '<a href="/?show=completed&amp;q=milk">Completed</a>',
        ]:
            with self.subTest(link=link):
                self.assertContains(response, link, count=1, html=True)

    def test_every_post_form_keeps_the_search(self):
        # On /?q=milk, "Milk the cow" (completed) is shown too, with its forms.
        for query in ["?show=active&q=milk", "?q=milk"]:
            with self.subTest(query=query):
                actions = page_parts(self.client.get("/" + query)).post_actions
                self.assertGreaterEqual(len(actions), 3)
                for action in actions:
                    path, mark, rest = action.partition("?")
                    self.assertEqual(mark + rest, query, action)

    def test_actions_go_back_to_the_search(self):
        def post(name, args, params, data=None):
            url = reverse(name, args=args) + "?" + urlencode(params)
            return self.client.post(url, data or {})

        extra = Todo.objects.create(title="Milk to delete")
        toggle = ("todo_toggle", [self.buy.pk])
        cases = [
            (
                ("todo_add", [], {"q": "milk"}, {"title": "Milk again"}),
                "/?q=milk",
            ),
            ((*toggle, {"q": "milk"}), "/?q=milk"),
            (
                ("todo_delete", [extra.pk], {"show": "active", "q": "milk"}),
                "/?show=active&q=milk",
            ),
            ((*toggle, {"q": "牛乳"}), "/?q=%E7%89%9B%E4%B9%B3"),
            ((*toggle, {"q": "buy milk"}), "/?q=buy+milk"),
            # The `&` stays inside q: it never becomes a second parameter.
            (
                (*toggle, {"q": "a&next=https://evil.example"}),
                "/?q=a%26next%3Dhttps%3A%2F%2Fevil.example",
            ),
            (
                (
                    "todo_delete_completed",
                    [],
                    {"q": "milk"},
                    {"ids": [self.cow.pk]},
                ),
                "/?q=milk",
            ),
        ]
        for args, location in cases:
            with self.subTest(name=args[0], params=args[2]):
                response = post(*args)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], location)

    def test_add_error_keeps_the_search(self):
        response = self.client.post(
            reverse("todo_add") + "?q=milk", {"title": "New", "due_date": "not-a-date"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid date.")
        self.assert_shown(response, ["Buy milk"], ["Call home"])
        self.assertContains(response, search_box("milk"), count=1, html=True)

    # Search: protect what already works.

    def test_search_changes_nothing(self):
        def rows():
            return list(Todo.objects.order_by("pk").values_list("pk", "done"))

        before = rows()
        self.search("milk")
        self.assertEqual(rows(), before)

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
        buy = Todo.objects.create(title="Buy milk", done=True)
        call = Todo.objects.create(title="Call home", done=True)
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
