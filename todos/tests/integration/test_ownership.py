"""Accounts (17): a person sees and changes only their own to-dos.

Ana is logged in. Ben has his own to-dos. To ana, ben's to-do must look like
one that does not exist: 404, and nothing changes.
"""

from django.urls import reverse

from todos import urls as todo_urls
from todos.models import Subtask, Todo
from todos.tests.integration.helpers import (
    LoggedInTestCase,
    count_elements,
    list_footer,
    make_user,
    page_parts,
    page_without_csrf,
)

# The addresses with no to-do id: the list itself, and the actions on it.
# Their tests are below (the list, the count, delete completed, add).
LIST_URLS = {"todo_list", "todo_add", "todo_delete_completed"}

# The addresses that take a step's id after the to-do's id.
SUBTASK_ID_URLS = {"subtask_done", "subtask_delete"}

# One row per (address name, method, data). Every address with an id must be here:
# test_every_url_is_in_the_matrix checks it.
MATRIX = [
    ("todo_toggle", "post", {"done": "1"}),
    ("todo_toggle", "post", {"done": "0"}),
    ("todo_delete", "post", {}),
    ("todo_edit", "get", {}),
    (
        "todo_edit",
        "post",
        {"title": "Hacked", "priority": "2", "repeat": "none"},
    ),
    ("subtask_list", "get", {}),
    ("subtask_add", "post", {"title": "Hacked step"}),
    ("subtask_done", "post", {"done": "1"}),
    ("subtask_done", "post", {"done": "0"}),
    ("subtask_delete", "post", {}),
]


def tables():
    """Every row of both tables: a snapshot to check that nothing changed."""
    return list(Todo.objects.values()), list(Subtask.objects.values())


def url_for(name, todo, step):
    args = [todo.pk, step.pk] if name in SUBTASK_ID_URLS else [todo.pk]
    return reverse(name, args=args)


class OwnershipTests(LoggedInTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ben = make_user("ben")

    def bens_todo(self, **fields):
        """A fresh to-do of ben's, with one step."""
        todo = self.make_todo(owner=self.ben, title="Ben's secret", **fields)
        step = Subtask.objects.create(todo=todo, title="Ben's step")
        return todo, step

    def anas_todo(self, **fields):
        """A fresh to-do of ana's, with one step."""
        todo = self.make_todo(title="Ana's own", **fields)
        step = Subtask.objects.create(todo=todo, title="Ana's step")
        return todo, step

    def send(self, method, url, data):
        if method == "get":
            return self.client.get(url, data)
        return self.client.post(url, data)

    # The list.

    def test_list_shows_only_my_todos(self):
        milk = self.make_todo(title="Buy milk")
        self.bens_todo()
        parts = page_parts(self.client.get("/"))
        self.assertEqual(parts.titles, ["Buy milk"])
        self.assertEqual([row.id for row in parts.rows], [f"todo-{milk.pk}"])

    def test_count_counts_only_mine(self):
        self.make_todo(title="Buy milk")
        done = self.make_todo(title="Call home", done=True)
        self.bens_todo()
        self.bens_todo(done=True)
        response = self.client.get("/")
        footer = list_footer("1 item left", completed_ids=[done.pk])
        self.assertInHTML(footer, page_without_csrf(response), count=1)

    def test_no_footer_when_only_another_person_has_todos(self):
        self.bens_todo()
        response = self.client.get("/")
        self.assertContains(
            response,
            "<li>Nothing to do yet. Add something above.</li>",
            count=1,
            html=True,
        )
        self.assertEqual(count_elements(response, "div", "list-footer"), 0)

    def test_search_filter_and_sort_show_only_mine(self):
        self.make_todo(title="Buy milk")
        self.make_todo(title="Milk done", done=True)
        self.bens_todo(notes="milk")
        self.make_todo(owner=self.ben, title="Ben's milk")
        self.make_todo(owner=self.ben, title="Ben's done milk", done=True)
        cases = [
            ({"q": "milk"}, ["Buy milk", "Milk done"]),
            ({"show": "active"}, ["Buy milk"]),
            ({"show": "completed"}, ["Milk done"]),
            ({"sort": "title"}, ["Buy milk", "Milk done"]),
            ({"sort": "due", "q": "milk"}, ["Buy milk", "Milk done"]),
        ]
        for params, titles in cases:
            with self.subTest(params=params):
                response = self.client.get("/", params)
                self.assertEqual(page_parts(response).titles, titles)

    def test_their_selected_todo_shows_no_pane(self):
        theirs, _ = self.bens_todo()
        self.make_todo(title="Buy milk")
        response = self.client.get("/", {"selected": theirs.pk})
        self.assertEqual(page_parts(response).panes, [])
        self.assertEqual(page_parts(response).selected_titles, [])

    # Add and delete completed.

    def test_add_makes_my_todo(self):
        self.client.post(reverse("todo_add"), {"title": "Buy milk"})
        self.assertEqual(Todo.objects.get().owner, self.user)

    def test_add_and_edit_ignore_a_posted_owner(self):
        self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "owner": str(self.ben.pk)}
        )
        milk = Todo.objects.get()
        self.assertEqual(milk.owner, self.user)
        self.client.post(
            reverse("todo_edit", args=[milk.pk]),
            {"title": "Buy oat milk", "owner": str(self.ben.pk)},
        )
        milk.refresh_from_db()
        self.assertEqual((milk.title, milk.owner), ("Buy oat milk", self.user))

    def test_delete_completed_never_deletes_theirs(self):
        mine = self.make_todo(title="Buy milk", done=True)
        theirs, _ = self.bens_todo(done=True)
        before_theirs = list(Todo.objects.filter(owner=self.ben).values())
        response = self.client.post(
            reverse("todo_delete_completed"), {"ids": [mine.pk, theirs.pk]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Todo.objects.filter(pk=mine.pk).exists())
        self.assertEqual(
            list(Todo.objects.filter(owner=self.ben).values()), before_theirs
        )
        self.assertEqual(Subtask.objects.filter(todo=theirs).count(), 1)

    # Every address with an id: another person's to-do is 404.

    def test_their_todo_is_404_everywhere(self):
        for name, method, data in MATRIX:
            with self.subTest(url=name, method=method, data=data):
                todo, step = self.bens_todo(done=data.get("done") == "0")
                before = tables()
                response = self.send(method, url_for(name, todo, step), data)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(tables(), before)

    def test_their_step_inside_my_todo_is_404(self):
        # The step is looked up inside the to-do in the address: ana's.
        for name in sorted(SUBTASK_ID_URLS):
            with self.subTest(url=name):
                mine, _ = self.anas_todo()
                _, their_step = self.bens_todo()
                before = tables()
                url = reverse(name, args=[mine.pk, their_step.pk])
                response = self.client.post(url, {"done": "1"})
                self.assertEqual(response.status_code, 404)
                self.assertEqual(tables(), before)

    def test_my_todo_is_not_404(self):
        # The same rows on ana's own to-do work: the 404 above comes from the
        # owner, not from a wrong address.
        for name, method, data in MATRIX:
            with self.subTest(url=name, method=method, data=data):
                todo, step = self.anas_todo(done=data.get("done") == "0")
                response = self.send(method, url_for(name, todo, step), data)
                self.assertIn(response.status_code, {200, 302})

    def test_every_url_is_in_the_matrix(self):
        names = {pattern.name for pattern in todo_urls.urlpatterns}
        in_matrix = {name for name, _method, _data in MATRIX}
        self.assertEqual(names - in_matrix - LIST_URLS, set())
        # And nothing in the matrix is an address that is gone.
        self.assertEqual((in_matrix | LIST_URLS) - names, set())
