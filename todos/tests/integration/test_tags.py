"""Tags (feature 14): put short words on to-dos, and click one to see only those.

Ana is logged in, with "My to-dos" (`self.todo_list`) and "Work". Ben has his
own "My to-dos". A tag belongs to the owner of the to-do's LIST.
"""

from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from todos.models import Tag, Todo, TodoList
from todos.tests.integration.helpers import (
    TEST_PASSWORD,
    LoggedInTestCase,
    count_elements,
    first_list,
    link_href,
    make_user,
    page_parts,
    page_without_csrf,
    pane_element,
    tag_list,
)


def tag_names(todo):
    return list(todo.tags.values_list("name", flat=True))


class TagTests(LoggedInTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ben = make_user("ben")
        cls.bens_list = first_list(cls.ben)
        cls.work = TodoList.objects.create(owner=cls.user, name="Work")

    def tagged(self, title, *names, todo_list=None, **fields):
        """A to-do of ana's (or in `todo_list`) with these tags."""
        todo = self.make_todo(todo_list=todo_list, title=title, **fields)
        todo.set_tags(names)
        return todo

    def tags_of(self, todo, query="", current=""):
        """The tag list of `todo`, with its names in a-b-c order."""
        names = [tag.name for tag in todo.tags.all()]
        return tag_list(todo.todo_list_id, names, query, current)

    # Saving tags.

    def test_add_saves_tags(self):
        response = self.client.post(
            self.add_url(), {"title": "Buy milk", "tag_names": "home, urgent"}
        )
        self.assertEqual(response.status_code, 302)
        milk = Todo.objects.get()
        self.assertEqual(tag_names(milk), ["home", "urgent"])
        self.assertEqual(
            list(Tag.objects.values_list("owner", flat=True)), [self.user.pk] * 2
        )

    def test_add_reuses_an_existing_tag(self):
        home = Tag.objects.create(owner=self.user, name="home")
        self.client.post(self.add_url(), {"title": "Buy milk", "tag_names": "Home"})
        self.assertEqual(list(Tag.objects.all()), [home])
        self.assertEqual(list(Todo.objects.get().tags.all()), [home])

    def test_the_same_tag_in_two_lists_is_one_row(self):
        self.client.post(self.add_url(), {"title": "Buy milk", "tag_names": "home"})
        self.client.post(
            self.add_url(self.work), {"title": "Fix the door", "tag_names": "home"}
        )
        self.assertEqual(Tag.objects.filter(name="home").count(), 1)

    def test_posting_a_tag_name_never_uses_another_persons_tag(self):
        bens = self.tagged("Ben's plan", "secret", todo_list=self.bens_list)
        bens_tag = bens.tags.get()
        self.client.post(self.add_url(), {"title": "Buy milk", "tag_names": "secret"})
        anas_tag = Todo.objects.get(title="Buy milk").tags.get()
        self.assertEqual(anas_tag.owner, self.user)
        self.assertNotEqual(anas_tag.pk, bens_tag.pk)
        self.assertEqual(list(bens.tags.all()), [bens_tag])
        bens_tag.refresh_from_db()
        self.assertEqual((bens_tag.owner, bens_tag.name), (self.ben, "secret"))
        self.assertEqual(Tag.objects.filter(name="secret").count(), 2)

    def test_editing_never_uses_another_persons_tag(self):
        self.tagged("Ben's plan", "secret", todo_list=self.bens_list)
        milk = self.make_todo(title="Buy milk")
        self.client.post(
            reverse("todo_edit", args=[milk.pk]),
            {"title": "Buy milk", "tag_names": "secret"},
        )
        self.assertEqual(milk.tags.get().owner, self.user)

    def test_bad_tags_keep_the_input(self):
        response = self.client.post(
            self.add_url(), {"title": "Buy milk", "tag_names": "a,b,c,d,e,f"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<ul class="errorlist" id="id_tag_names_error">'
            "<li>At most 5 tags on one to-do.</li></ul>",
            count=1,
            html=True,
        )
        self.assertContains(
            response,
            '<input type="text" name="tag_names" value="a,b,c,d,e,f" '
            'placeholder="home, urgent" maxlength="200" aria-invalid="true" '
            'aria-describedby="id_tag_names_helptext id_tag_names_error" '
            'id="id_tag_names">',
            count=1,
            html=True,
        )
        self.assertFalse(Todo.objects.exists())

    def test_add_form_has_the_tags_box(self):
        response = self.client.get(self.list_url())
        for element in [
            '<label for="id_tag_names">Tags:</label>',
            '<input type="text" name="tag_names" placeholder="home, urgent" '
            'maxlength="200" aria-describedby="id_tag_names_helptext" '
            'id="id_tag_names">',
            '<span class="helptext" id="id_tag_names_helptext">'
            "separated by commas</span>",
        ]:
            with self.subTest(element=element):
                self.assertContains(response, element, count=1, html=True)

    def test_edit_replaces_tags(self):
        milk = self.tagged("Buy milk", "home")
        url = reverse("todo_edit", args=[milk.pk])
        response = self.client.get(url)
        self.assertContains(
            response,
            '<input type="text" name="tag_names" value="home" maxlength="200" '
            'aria-describedby="id_tag_names_helptext" id="id_tag_names">',
            count=1,
            html=True,
        )
        self.client.post(url, {"title": "Buy milk", "tag_names": "work"})
        self.assertEqual(tag_names(milk), ["work"])

    def test_moving_a_todo_keeps_its_tags(self):
        milk = self.tagged("Buy milk", "home")
        self.client.post(
            reverse("todo_edit", args=[milk.pk]),
            {"title": "Buy milk", "todo_list": self.work.pk, "tag_names": "home"},
        )
        milk.refresh_from_db()
        self.assertEqual(milk.todo_list, self.work)
        self.assertEqual(milk.tags.get().owner, self.user)

    def test_unused_tag_is_kept(self):
        milk = self.tagged("Buy milk", "home")
        self.client.post(
            reverse("todo_edit", args=[milk.pk]), {"title": "Buy milk", "tag_names": ""}
        )
        self.assertEqual(tag_names(milk), [])
        self.assertTrue(Tag.objects.filter(owner=self.user, name="home").exists())

    # The tags on each row.

    def test_tag_links_on_each_row(self):
        self.tagged("Buy milk", "urgent", "home")
        response = self.client.get(self.list_url())
        list_id = self.todo_list.pk
        self.assertContains(
            response,
            '<ul class="tags" aria-label="Tags">'
            f'<li><a class="tag" href="/lists/{list_id}/?tag=home">home</a></li>'
            f'<li><a class="tag" href="/lists/{list_id}/?tag=urgent">urgent</a></li>'
            "</ul>",
            count=1,
            html=True,
        )

    def test_no_tags_no_list(self):
        self.make_todo(title="Call mum")
        response = self.client.get(self.list_url())
        self.assertEqual(page_parts(response).titles, ["Call mum"])
        self.assertEqual(count_elements(response, "ul", "tags"), 0)

    def test_tag_link_keeps_the_other_settings(self):
        milk = self.tagged("Buy milk", "home")
        response = self.client.get(self.list_url(query="?show=active&q=milk"))
        list_id = self.todo_list.pk
        self.assertContains(
            response,
            '<ul class="tags" aria-label="Tags"><li><a class="tag" '
            f'href="/lists/{list_id}/?show=active&amp;q=milk&amp;tag=home">home</a>'
            "</li></ul>",
            count=1,
            html=True,
        )
        self.assertContains(
            response, self.tags_of(milk, "?show=active&q=milk"), count=1, html=True
        )

    def test_tag_link_drops_the_selection(self):
        # A tag shows a new group: the pane closes, like a new page.
        milk = self.tagged("Buy milk", "home")
        response = self.client.get(
            self.list_url(query=f"?sort=title&selected={milk.pk}")
        )
        # Twice: on the row and in the pane.
        self.assertContains(
            response, self.tags_of(milk, "?sort=title"), count=2, html=True
        )

    def test_tag_link_is_safe(self):
        self.tagged("Odd", "a&show=x", "<b>")
        response = self.client.get(self.list_url())
        list_id = self.todo_list.pk
        self.assertContains(
            response,
            '<ul class="tags" aria-label="Tags">'
            f'<li><a class="tag" href="/lists/{list_id}/?tag=%3Cb%3E">&lt;b&gt;</a></li>'
            f'<li><a class="tag" href="/lists/{list_id}/?tag=a%26show%3Dx">a&amp;show=x</a></li>'
            "</ul>",
            count=1,
            html=True,
        )
        self.assertNotContains(response, "<b>")

    def test_tag_link_with_a_space_works(self):
        self.tagged("Buy milk", "go shopping")
        self.make_todo(title="Call mum")
        page = self.client.get(self.list_url())
        href = link_href(page, "go shopping")
        self.assertEqual(href, self.list_url(query="?tag=go%20shopping"))
        page = self.client.get(href)
        self.assertEqual(page_parts(page).titles, ["Buy milk"])
        self.assertContains(
            page,
            '<p class="current-tag">Tagged <strong>go shopping</strong> · '
            f'<a href="{self.list_url()}">Show all tags</a></p>',
            count=1,
            html=True,
        )

    def test_tags_come_in_name_order_also_after_the_title_sort(self):
        self.tagged("B", "zebra", "apple")
        self.tagged("A", "mango")
        response = self.client.get(self.list_url(query="?sort=title"))
        self.assertEqual(page_parts(response).titles, ["A", "B"])
        list_id = self.todo_list.pk
        self.assertContains(
            response,
            tag_list(list_id, ["apple", "zebra"], "?sort=title"),
            count=1,
            html=True,
        )

    # The tag filter.

    def test_tag_filter_shows_only_tagged_todos(self):
        milk = self.tagged("Buy milk", "home", "urgent")
        self.make_todo(title="Call mum")
        response = self.client.get(self.list_url(query="?tag=home"))
        self.assertEqual(page_parts(response).titles, ["Buy milk"])
        self.assertContains(
            response,
            '<p class="current-tag">Tagged <strong>home</strong> · '
            f'<a href="{self.list_url()}">Show all tags</a></p>',
            count=1,
            html=True,
        )
        # The chosen tag's link is marked.
        self.assertContains(
            response, self.tags_of(milk, "", current="home"), count=1, html=True
        )

    def test_no_current_tag_line_without_a_tag(self):
        self.tagged("Buy milk", "home")
        response = self.client.get(self.list_url())
        self.assertEqual(count_elements(response, "p", "current-tag"), 0)

    def test_tag_filter_cleans_the_tag(self):
        self.tagged("Buy milk", "home")
        response = self.client.get(self.list_url(query="?tag=%20HOME%20"))
        self.assertEqual(page_parts(response).titles, ["Buy milk"])
        self.assertContains(response, "<strong>home</strong>", count=1, html=True)

    def test_tag_filter_is_within_the_current_list(self):
        self.tagged("Buy milk", "home")
        self.tagged("Fix the door", "home", todo_list=self.work)
        response = self.client.get(self.list_url(query="?tag=home"))
        self.assertEqual(page_parts(response).titles, ["Buy milk"])
        response = self.client.get(self.list_url(self.work, "?tag=home"))
        self.assertEqual(page_parts(response).titles, ["Fix the door"])

    def test_tag_filter_works_with_show_and_search(self):
        self.tagged("Buy milk", "home")
        self.tagged("Milk done", "home", done=True)
        self.tagged("Buy bread", "home")
        self.tagged("Buy more milk", "work")
        response = self.client.get(self.list_url(query="?show=active&q=milk&tag=home"))
        self.assertEqual(page_parts(response).titles, ["Buy milk"])
        # "Show all tags" keeps the filter and the search.
        self.assertEqual(
            link_href(response, "Show all tags"),
            self.list_url(query="?show=active&q=milk"),
        )

    def test_a_tag_with_no_todos_says_so(self):
        self.tagged("Buy milk", "home")
        response = self.client.get(self.list_url(query="?tag=banana"))
        self.assertEqual(page_parts(response).titles, [])
        self.assertContains(
            response, '<li>No to-dos tagged "banana".</li>', count=1, html=True
        )

    def test_a_search_message_wins_over_the_tag_message(self):
        self.tagged("Buy milk", "home")
        response = self.client.get(self.list_url(query="?q=bread&tag=home"))
        self.assertContains(
            response, '<li>No to-dos match "bread".</li>', count=1, html=True
        )

    def test_tag_filter_is_the_same_whether_or_not_someone_has_the_tag(self):
        self.tagged("Buy milk", "home")
        url = self.list_url(query="?tag=secret")
        before = page_without_csrf(self.client.get(url))
        self.tagged("Ben's plan", "secret", todo_list=self.bens_list)
        after = self.client.get(url)
        self.assertEqual(page_without_csrf(after), before)
        self.assertContains(
            after, '<li>No to-dos tagged "secret".</li>', count=1, html=True
        )

    def test_another_persons_tags_never_appear(self):
        self.tagged("Buy milk", "home")
        self.tagged("Ben's plan", "bobsecret", "home", todo_list=self.bens_list)
        for query in ["", "?tag=home", "?tag=bobsecret"]:
            with self.subTest(query=query):
                response = self.client.get(self.list_url(query=query))
                titles = [] if query == "?tag=bobsecret" else ["Buy milk"]
                self.assertEqual(page_parts(response).titles, titles)
                link = (
                    f'<a class="tag" href="/lists/{self.todo_list.pk}/?tag=bobsecret">'
                    "bobsecret</a>"
                )
                self.assertContains(response, link, count=0, html=True)
                self.assertEqual(count_elements(response, "ul", "tags"), len(titles))

    def test_a_tag_of_the_same_name_from_another_person_does_not_match(self):
        # A broken row (never made by the app): ana's to-do with ben's tag.
        # The filter asks for the LIST owner's tag, so it does not match.
        milk = self.make_todo(title="Buy milk")
        bens_home = Tag.objects.create(owner=self.ben, name="home")
        milk.tags.add(bens_home)
        response = self.client.get(self.list_url(query="?tag=home"))
        self.assertEqual(page_parts(response).titles, [])

    def test_every_post_form_keeps_the_tag(self):
        self.tagged("Buy milk", "home", done=True)
        self.tagged("Call mum", "home")
        for list_query in ["?tag=home", "?show=active&tag=home"]:
            with self.subTest(query=list_query):
                actions = page_parts(
                    self.client.get(self.list_url(query=list_query))
                ).post_actions
                self.assertGreaterEqual(len(actions), 3)
                for action in actions:
                    _path, mark, rest = action.partition("?")
                    self.assertEqual(mark + rest, list_query, action)

    def test_filter_and_sort_links_keep_the_tag(self):
        self.tagged("Buy milk", "home")
        response = self.client.get(self.list_url(query="?tag=home"))
        self.assertEqual(
            link_href(response, "Active"), self.list_url(query="?show=active&tag=home")
        )
        self.assertEqual(
            link_href(response, "Title"), self.list_url(query="?sort=title&tag=home")
        )

    def test_search_form_keeps_the_tag(self):
        self.tagged("Buy milk", "home")
        response = self.client.get(self.list_url(query="?tag=home"))
        self.assertContains(
            response,
            '<input type="hidden" name="tag" value="home">',
            count=1,
            html=True,
        )

    def test_done_keeps_the_tag(self):
        milk = self.tagged("Buy milk", "home")
        response = self.client.post(
            reverse("todo_toggle", args=[milk.pk]) + "?tag=home", {"done": "1"}
        )
        self.assertEqual(response["Location"], self.list_url(query="?tag=home"))

    def test_add_keeps_the_tag(self):
        response = self.client.post(
            self.add_url(query="?tag=home"), {"title": "Buy milk", "tag_names": "home"}
        )
        self.assertEqual(response["Location"], self.list_url(query="?tag=home"))

    def test_count_ignores_the_tag(self):
        self.tagged("Buy milk", "home")
        self.make_todo(title="Call mum")
        response = self.client.get(self.list_url(query="?tag=home"))
        self.assertContains(
            response, '<p class="count">2 items left</p>', count=1, html=True
        )

    # The details pane.

    def test_pane_shows_the_tags(self):
        milk = self.tagged("Buy milk", "urgent", "home")
        Todo.objects.filter(pk=milk.pk).update(
            created_at=datetime(2026, 10, 1, 3, 0, tzinfo=UTC)
        )
        response = self.client.get(self.list_url(query=f"?selected={milk.pk}"))
        pane = pane_element(
            milk,
            created="1 Oct 2026",
            close_url=self.list_url(),
            tags=self.tags_of(milk),
        )
        self.assertInHTML(pane, page_without_csrf(response), count=1)

    def test_pane_has_no_tags_row_without_tags(self):
        milk = self.make_todo(title="Buy milk")
        response = self.client.get(self.list_url(query=f"?selected={milk.pk}"))
        self.assertNotIn("ul", page_parts(response).pane_tags)
        self.assertEqual(page_parts(response).pane_tags.count("dt"), 4)

    # Queries.

    def page_queries(self, query=""):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.list_url(query=query))
        self.assertEqual(response.status_code, 200)
        return len(queries)

    def test_list_page_query_count_does_not_grow(self):
        self.tagged("Buy milk", "home", "urgent")
        one = self.page_queries()
        for index in range(4):
            self.tagged(f"To-do {index}", "home", f"tag {index}")
        self.assertEqual(self.page_queries(), one)

    def test_selecting_a_tagged_todo_adds_no_queries(self):
        # The prefetch must come before selected_todo: then the pane's tags
        # come from the same prefetch as the rows.
        milk = self.tagged("Buy milk", "home", "urgent")
        self.tagged("Call mum", "home", "family")
        self.assertEqual(self.page_queries(f"?selected={milk.pk}"), self.page_queries())

    def test_tag_filter_with_two_tags_shows_each_todo_once(self):
        self.tagged("Buy milk", "home", "urgent")
        response = self.client.get(self.list_url(query="?tag=home"))
        self.assertEqual(page_parts(response).titles, ["Buy milk"])


class TagAdminTests(LoggedInTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff = get_user_model().objects.create_superuser(
            "boss", password=TEST_PASSWORD
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_admin_tags_are_read_only(self):
        milk = self.make_todo(title="Buy milk")
        milk.set_tags(["home"])
        tag = milk.tags.get()
        self.assertEqual(self.client.get("/admin/todos/tag/").status_code, 200)
        self.assertEqual(self.client.get("/admin/todos/tag/add/").status_code, 403)
        response = self.client.get(f"/admin/todos/tag/{tag.pk}/change/")
        self.assertEqual(response.status_code, 200)
        fields = response.context["adminform"].form.fields
        self.assertNotIn("name", fields)
        self.assertNotIn("owner", fields)
        response = self.client.get(f"/admin/todos/todo/{milk.pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("tags", response.context["adminform"].form.fields)
