"""Lists (feature 13): one list at a time, and making, renaming and deleting lists.

Ana (logged in) has "My to-dos" (`self.todo_list`) and "Work". Ben has "My
to-dos" and "Secret". The new addresses are written out ("/lists/new/"), so a
test fails with a clear status when an address is missing.
"""

from django.contrib.auth import get_user_model
from django.test import Client

from todos.models import Todo, TodoList
from todos.tests.integration.helpers import (
    LOGIN_URL,
    SIGNUP_URL,
    TEST_PASSWORD,
    LoggedInTestCase,
    account_bar,
    first_list,
    link_href,
    list_path,
    make_user,
    page_forms,
    page_parts,
    page_post_forms,
    page_without_csrf,
    send_form,
)

NEW_LIST_URL = "/lists/new/"


def lists_nav(lists, current=None):
    """The whole <nav> of the person's lists, exactly: one link per list, in
    order, the open one marked, then "New list".
    """
    links = ""
    for todo_list in lists:
        mark = ' aria-current="page"' if todo_list == current else ""
        links += f'<a href="{list_path(todo_list.pk)}"{mark}>{todo_list.name}</a>'
    return (
        '<nav class="lists" aria-label="Lists">'
        f'{links}<a href="{NEW_LIST_URL}">New list</a>'
        "</nav>"
    )


def name_form(action, value="", cancel_url=None, error=None):
    """The whole name form of the "New list" and "Rename or delete" pages."""
    value_attr = f' value="{value}"' if value else ""
    error_list = (
        f'<ul class="errorlist" id="id_name_error"><li>{error}</li></ul>'
        if error
        else ""
    )
    invalid = ' aria-invalid="true" aria-describedby="id_name_error"' if error else ""
    cancel = f'<a href="{cancel_url}">Cancel</a>' if cancel_url else ""
    return (
        f'<form class="list-name" method="post" action="{action}">'
        '<div class="field"><label for="id_name">Name:</label>'
        f"{error_list}"
        f'<input type="text" name="name"{value_attr} maxlength="50" required'
        f'{invalid} id="id_name" autofocus></div>'
        f'<div class="actions"><button type="submit">Save</button>{cancel}</div>'
        "</form>"
    )


class ListTestCase(LoggedInTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.work = TodoList.objects.create(owner=cls.user, name="Work")
        cls.ben = make_user("ben")
        cls.secret = TodoList.objects.create(owner=cls.ben, name="Secret")

    def anas_lists(self):
        return list(TodoList.objects.filter(owner=self.user))


class HomeTests(ListTestCase):
    def test_home_goes_to_the_first_list(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/lists/{self.todo_list.pk}/")

    def test_home_drops_the_list_settings(self):
        response = self.client.get("/?show=active")
        self.assertEqual(response["Location"], f"/lists/{self.todo_list.pk}/")

    def test_home_with_no_list_goes_to_new_list(self):
        TodoList.objects.filter(owner=self.user).delete()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], NEW_LIST_URL)

    def test_no_list_new_list_page(self):
        # A person with no list can still log out, and has no Cancel (it would
        # come back here).
        TodoList.objects.filter(owner=self.user).delete()
        response = self.client.get(NEW_LIST_URL)
        self.assertEqual(response.status_code, 200)
        page = page_without_csrf(response)
        self.assertInHTML(account_bar("ana"), page, count=1)
        self.assertInHTML(name_form(NEW_LIST_URL), page, count=1)
        self.assertContains(response, "<h1>New list</h1>", count=1, html=True)

    def test_login_and_signup_land_on_the_first_list(self):
        with self.subTest("log in"):
            client = Client()
            page = client.get(LOGIN_URL)
            page = send_form(
                client, page, "Log in", username="ben", password=TEST_PASSWORD
            )
            self.assertEqual(
                page.redirect_chain,
                [("/", 302), (list_path(first_list(self.ben).pk), 302)],
            )
        with self.subTest("sign up"):
            client = Client()
            page = client.get(SIGNUP_URL)
            page = send_form(
                client,
                page,
                "Sign up",
                username="cai",
                password1=TEST_PASSWORD,
                password2=TEST_PASSWORD,
            )
            cai = get_user_model().objects.get(username="cai")
            self.assertEqual(
                page.redirect_chain, [("/", 302), (list_path(first_list(cai).pk), 302)]
            )
            self.assertContains(page, "<h1>My to-dos</h1>", count=1, html=True)

    def test_signup_makes_my_todos(self):
        client = Client()
        page = client.get(SIGNUP_URL)
        send_form(
            client,
            page,
            "Sign up",
            username="cai",
            password1=TEST_PASSWORD,
            password2=TEST_PASSWORD,
        )
        cai = get_user_model().objects.get(username="cai")
        self.assertEqual(
            list(TodoList.objects.values_list("name", flat=True).filter(owner=cai)),
            ["My to-dos"],
        )


class ListPageTests(ListTestCase):
    def test_list_page_shows_only_that_list(self):
        self.make_todo(title="Buy milk")
        report = self.make_todo(title="Write report", todo_list=self.work)
        response = self.client.get(f"/lists/{self.work.pk}/")
        parts = page_parts(response)
        self.assertEqual(parts.titles, ["Write report"])
        self.assertEqual([row.id for row in parts.rows], [f"todo-{report.pk}"])
        self.assertContains(response, "<h1>Work</h1>", count=1, html=True)
        self.assertContains(
            response, "<title>Work – To-do list</title>", count=1, html=True
        )

    def test_list_links(self):
        response = self.client.get(f"/lists/{self.work.pk}/")
        self.assertContains(
            response,
            lists_nav([self.todo_list, self.work], current=self.work),
            count=1,
            html=True,
        )
        parts = page_parts(response)
        self.assertEqual(parts.current_lists, ["Work"])
        self.assertEqual(parts.current_links, ["All"])  # the filter, as before
        self.assertEqual(link_href(response, "New list"), NEW_LIST_URL)
        self.assertEqual(
            link_href(response, "Rename or delete Work"), f"/lists/{self.work.pk}/edit/"
        )

    def test_add_goes_into_the_open_list(self):
        response = self.client.post(
            f"/lists/{self.work.pk}/add/?show=active", {"title": "Write report"}
        )
        todo = Todo.objects.get()
        self.assertEqual((todo.todo_list, todo.owner), (self.work, self.user))
        self.assertEqual(response["Location"], f"/lists/{self.work.pk}/?show=active")

    def test_count_is_per_list(self):
        self.make_todo(title="Buy milk")
        self.make_todo(title="Call home")
        self.make_todo(title="Write report", todo_list=self.work)
        response = self.client.get(f"/lists/{self.work.pk}/")
        self.assertInHTML(
            self.list_footer("1 item left", todo_list=self.work),
            page_without_csrf(response),
            count=1,
        )

    def test_delete_completed_only_in_this_list(self):
        mine = self.make_todo(title="Buy milk", done=True)
        report = self.make_todo(title="Write report", done=True, todo_list=self.work)
        page = self.client.get(f"/lists/{self.work.pk}/")
        self.assertInHTML(
            self.list_footer("0 items left", [report.pk], todo_list=self.work),
            page_without_csrf(page),
            count=1,
        )
        response = self.client.post(
            f"/lists/{self.work.pk}/delete-completed/", {"ids": [mine.pk, report.pk]}
        )
        self.assertEqual(response["Location"], f"/lists/{self.work.pk}/")
        self.assertEqual(list(Todo.objects.all()), [mine])

    def test_search_is_per_list(self):
        self.make_todo(title="Buy milk")
        work_milk = self.make_todo(title="Buy milk", todo_list=self.work)
        response = self.client.get(f"/lists/{self.work.pk}/", {"q": "milk"})
        parts = page_parts(response)
        self.assertEqual(parts.titles, ["Buy milk"])
        self.assertEqual([row.id for row in parts.rows], [f"todo-{work_milk.pk}"])

    def test_toggle_and_delete_go_back_to_the_todos_list(self):
        for name, data in [("toggle", {"done": "1"}), ("delete", {})]:
            with self.subTest(name):
                todo = self.make_todo(title="Write report", todo_list=self.work)
                response = self.client.post(f"/{todo.pk}/{name}/?show=active", data)
                self.assertEqual(
                    response["Location"], f"/lists/{self.work.pk}/?show=active"
                )

    def test_missing_list_is_404(self):
        for method, url in [
            ("get", "/lists/999/"),
            ("post", "/lists/999/add/"),
            ("post", "/lists/999/delete-completed/"),
            ("get", "/lists/999/edit/"),
            ("post", "/lists/999/edit/"),
            ("post", "/lists/999/delete/"),
            ("get", f"/lists/{'9' * 25}/"),
        ]:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, {"name": "x"})
                self.assertEqual(response.status_code, 404)


class NewListTests(ListTestCase):
    def test_new_list_page(self):
        response = self.client.get(NEW_LIST_URL)
        self.assertContains(response, "<h1>New list</h1>", count=1, html=True)
        # She has lists: Cancel goes to "/", her first list.
        self.assertInHTML(
            name_form(NEW_LIST_URL, cancel_url="/"),
            page_without_csrf(response),
            count=1,
        )

    def test_create_list(self):
        response = self.client.post(NEW_LIST_URL, {"name": " Shopping "})
        [shopping] = TodoList.objects.filter(name="Shopping")
        self.assertEqual(shopping.owner, self.user)
        self.assertEqual(response["Location"], f"/lists/{shopping.pk}/")
        self.assertEqual(len(self.anas_lists()), 3)

    def test_create_list_with_a_used_name(self):
        response = self.client.post(NEW_LIST_URL, {"name": "work"})
        self.assertEqual(response.status_code, 200)
        self.assertInHTML(
            name_form(
                NEW_LIST_URL,
                value="work",
                cancel_url="/",
                error="You already have a list called &quot;work&quot;.",
            ),
            page_without_csrf(response),
            count=1,
        )
        self.assertEqual(len(self.anas_lists()), 2)

    def test_create_list_may_use_another_persons_name(self):
        response = self.client.post(NEW_LIST_URL, {"name": "Secret"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TodoList.objects.filter(owner=self.user, name="Secret"))

    def test_create_list_ignores_a_posted_owner(self):
        self.client.post(NEW_LIST_URL, {"name": "Shopping", "owner": self.ben.pk})
        self.assertEqual(TodoList.objects.get(name="Shopping").owner, self.user)

    def test_new_list_form_works_with_csrf_checks_on(self):
        client = self.csrf_client()
        page = client.get(NEW_LIST_URL)
        [form] = page_post_forms(page)
        self.assertIn("csrfmiddlewaretoken", form.fields)
        response = client.post(form.action, form.data(name="Shopping"))
        self.assertEqual(response.status_code, 302)


class RenameOrDeleteTests(ListTestCase):
    def edit_url(self):
        return f"/lists/{self.work.pk}/edit/"

    def test_rename_page(self):
        response = self.client.get(self.edit_url())
        self.assertContains(
            response, "<h1>Rename or delete Work</h1>", count=1, html=True
        )
        self.assertInHTML(
            name_form(
                self.edit_url(), value="Work", cancel_url=f"/lists/{self.work.pk}/"
            ),
            page_without_csrf(response),
            count=1,
        )

    def test_rename_list(self):
        response = self.client.post(self.edit_url(), {"name": "Office"})
        self.work.refresh_from_db()
        self.assertEqual(self.work.name, "Office")
        self.assertEqual(response["Location"], f"/lists/{self.work.pk}/")

    def test_rename_to_another_case_of_itself(self):
        self.client.post(self.edit_url(), {"name": "WORK"})
        self.work.refresh_from_db()
        self.assertEqual(self.work.name, "WORK")

    def test_rename_to_a_used_name(self):
        response = self.client.post(self.edit_url(), {"name": "my TO-DOS"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<ul class="errorlist" id="id_name_error">'
            "<li>You already have a list called &quot;my TO-DOS&quot;.</li></ul>",
            count=1,
            html=True,
        )
        self.work.refresh_from_db()
        self.assertEqual(self.work.name, "Work")

    def test_delete_button_says_how_many(self):
        cases = [
            (0, '<button type="submit">Delete list</button>'),
            (1, '<button type="submit">Delete list and its 1 to-do</button>'),
            (3, '<button type="submit">Delete list and its 3 to-dos</button>'),
        ]
        for count, button in cases:
            with self.subTest(count=count):
                Todo.objects.filter(todo_list=self.work).delete()
                for n in range(count):
                    self.make_todo(title=f"Task {n}", todo_list=self.work)
                response = self.client.get(self.edit_url())
                self.assertContains(response, button, count=1, html=True)
                [delete] = [
                    form
                    for form in page_forms(response)
                    if form.action == f"/lists/{self.work.pk}/delete/"
                ]
                self.assertEqual(delete.method, "post")

    def test_delete_list_deletes_its_todos(self):
        milk = self.make_todo(title="Buy milk")
        self.make_todo(title="Write report", todo_list=self.work)
        self.make_todo(title="Call Bob", todo_list=self.work)
        response = self.client.post(f"/lists/{self.work.pk}/delete/")
        self.assertEqual(response["Location"], "/")
        self.assertFalse(TodoList.objects.filter(pk=self.work.pk).exists())
        self.assertEqual(list(Todo.objects.all()), [milk])

    def test_delete_last_list_goes_to_new_list(self):
        self.client.post(f"/lists/{self.work.pk}/delete/")
        self.client.post(f"/lists/{self.todo_list.pk}/delete/")
        self.assertEqual(self.anas_lists(), [])
        response = self.client.get("/")
        self.assertEqual(response["Location"], NEW_LIST_URL)

    def test_delete_list_refuses_get(self):
        response = self.client.get(f"/lists/{self.work.pk}/delete/")
        self.assertEqual(response.status_code, 405)
        self.assertTrue(TodoList.objects.filter(pk=self.work.pk).exists())


class MoveTests(ListTestCase):
    def test_edit_page_list_choice(self):
        todo = self.make_todo(title="Write report")
        response = self.client.get(f"/{todo.pk}/edit/")
        self.assertContains(
            response, '<label for="id_todo_list">List:</label>', count=1, html=True
        )
        self.assertContains(
            response,
            '<select name="todo_list" id="id_todo_list">'
            f'<option value="{self.todo_list.pk}" selected>My to-dos</option>'
            f'<option value="{self.work.pk}">Work</option>'
            "</select>",
            count=1,
            html=True,
        )

    def test_move_todo_to_another_list(self):
        todo = self.make_todo(title="Write report")
        page = self.client.get(f"/{todo.pk}/edit/?show=active")
        [form] = page_post_forms(page)
        response = self.client.post(form.action, form.data(todo_list=self.work.pk))
        todo.refresh_from_db()
        self.assertEqual((todo.todo_list, todo.owner), (self.work, self.user))
        # Back to the list it came from, with the same filter.
        self.assertEqual(
            response["Location"], f"/lists/{self.todo_list.pk}/?show=active"
        )

    def test_edit_cancel_goes_to_the_todos_list(self):
        todo = self.make_todo(title="Write report", todo_list=self.work)
        page = self.client.get(f"/{todo.pk}/edit/?show=active")
        self.assertEqual(
            link_href(page, "Cancel"), f"/lists/{self.work.pk}/?show=active"
        )

    def test_move_to_another_users_list_is_refused(self):
        todo = self.make_todo(title="Write report")
        response = self.client.post(
            f"/{todo.pk}/edit/", {"title": "Write report", "todo_list": self.secret.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<ul class="errorlist" id="id_todo_list_error"><li>Select a valid choice. '
            "That choice is not one of the available choices.</li></ul>",
            count=1,
            html=True,
        )
        todo.refresh_from_db()
        self.assertEqual((todo.todo_list, todo.owner), (self.todo_list, self.user))
