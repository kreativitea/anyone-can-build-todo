"""Subtasks (feature 15): small steps inside one to-do, on their own page.

In the code and the addresses the word is "subtask"; on the page it is "step".
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from todos.models import Subtask, Todo
from todos.tests.integration.helpers import (
    LoggedInTestCase,
    page_parts,
    page_without_csrf,
    pane_element,
    show_date,
    title_element,
    toggle_form,
)


def step_row(todo, step, query=""):
    """One step on the steps page, exactly: its title, Done or Undo, Delete."""
    title = escape(step.title)
    if step.done:
        toggle = (
            f'<button type="submit" name="done" value="0" aria-label="Undo {title}">'
            "Undo</button>"
        )
    else:
        toggle = (
            f'<button type="submit" name="done" value="1" aria-label="Done {title}">'
            "Done</button>"
        )
    return (
        f'<li class="{"done" if step.done else ""}">'
        f'<span class="title">{title}</span>'
        f'<form method="post" action="/{todo.pk}/subtasks/{step.pk}/done/{query}">'
        f"{toggle}</form>"
        f'<form method="post" action="/{todo.pk}/subtasks/{step.pk}/delete/{query}">'
        f'<button type="submit" aria-label="Delete {title}">Delete</button></form>'
        "</li>"
    )


def add_step_form(todo, box, error="", query=""):
    """The "New step" form on the steps page, exactly. `box` is the <input>."""
    return (
        f'<form class="add-step" method="post" action="/{todo.pk}/subtasks/add/{query}">'
        f"{error}"
        '<label for="id_title">New step:</label>'
        f"{box}"
        '<button type="submit">Add step</button>'
        "</form>"
    )


EMPTY_BOX = (
    '<input type="text" name="title" maxlength="200" required id="id_title" autofocus>'
)


def progress_link(todo, done, total, query=""):
    """The "1 of 3 steps" line on a list row, exactly: a link in its own
    <small class="progress">, last inside the title block (under the title)."""
    return (
        '<small class="progress">'
        f'<a href="/{todo.pk}/subtasks/{escape(query)}" '
        f'aria-label="{done} of {total} steps for {escape(todo.title)}">'
        f"{done} of {total} steps</a></small>"
    )


def list_row(todo, progress=""):
    """One row of the list, exactly; `progress` is the progress line or "".

    The progress goes INSIDE the title block, so on a phone the title keeps
    the full width instead of sharing it with one more item beside the buttons.
    """
    return (
        f'<li id="todo-{todo.pk}" class="{"done" if todo.done else ""}">'
        f"{title_element(todo, progress=progress)}"
        f'<a class="edit" href="/{todo.pk}/edit/" '
        f'aria-label="Edit {escape(todo.title)}">Edit</a>'
        f"{toggle_form(todo, todo.done)}"
        f'<form method="post" action="/{todo.pk}/delete/">'
        '<button type="submit">Delete</button></form>'
        "</li>"
    )


class SubtaskTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.cake = self.make_todo(title="Bake a cake")
        self.flour = Subtask.objects.create(
            todo=self.cake, title="Buy flour", done=True
        )
        self.eggs = Subtask.objects.create(todo=self.cake, title="Buy eggs")
        self.bake = Subtask.objects.create(todo=self.cake, title="Bake")

    def steps_url(self, query="", todo=None):
        return reverse("subtask_list", args=[(todo or self.cake).pk]) + query

    def url(self, name, step=None, query="", todo=None):
        todo = todo or self.cake
        args = [todo.pk] if step is None else [todo.pk, step.pk]
        return reverse(name, args=args) + query

    def step_titles(self, todo=None):
        return list(
            Subtask.objects.filter(todo=todo or self.cake).values_list(
                "title", flat=True
            )
        )

    def step_states(self):
        return list(Subtask.objects.order_by("pk").values_list("title", "done"))

    # Subtasks: new behaviour.

    def test_steps_page_shows_the_steps(self):
        response = self.client.get(self.steps_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Steps: Bake a cake</title>", html=True)
        self.assertContains(response, "<h1>Steps: Bake a cake</h1>", html=True)
        self.assertEqual(page_parts(response).titles, ["Buy flour", "Buy eggs", "Bake"])
        rows = "".join(
            step_row(self.cake, step) for step in [self.flour, self.eggs, self.bake]
        )
        self.assertInHTML(
            f'<ul class="steps">{rows}</ul>', page_without_csrf(response), count=1
        )
        self.assertContains(
            response,
            '<button type="submit" name="done" value="0" '
            'aria-label="Undo Buy flour">Undo</button>',
            count=1,
            html=True,
        )
        self.assertContains(
            response,
            '<button type="submit" name="done" value="1" '
            'aria-label="Done Bake">Done</button>',
            count=1,
            html=True,
        )
        self.assertContains(
            response, '<label for="id_title">New step:</label>', count=1, html=True
        )
        self.assertInHTML(
            add_step_form(self.cake, EMPTY_BOX), page_without_csrf(response), count=1
        )
        self.assertContains(
            response,
            f"<a href='{self.list_url()}'>Back to the list</a>",
            count=1,
            html=True,
        )

    def test_titles_are_escaped(self):
        # A title with HTML in it is shown as text, everywhere: never |safe.
        todo = self.make_todo(title='<b>"x</b>')
        step = Subtask.objects.create(todo=todo, title='"><img src=x onerror=alert(1)>')
        page = self.client.get(self.steps_url(todo=todo))
        self.assertContains(
            page, "<h1>Steps: &lt;b&gt;&quot;x&lt;/b&gt;</h1>", count=1, html=True
        )
        # Raw text, not html=True: the HTML reader reads the inside of <title>
        # as plain text, so "<b>" and "&lt;b&gt;" would look the same to it.
        self.assertIn(
            "<title>Steps: &lt;b&gt;&quot;x&lt;/b&gt;</title>", page.content.decode()
        )
        self.assertInHTML(step_row(todo, step), page_without_csrf(page), count=1)
        self.assertNotIn("<img", page.content.decode())

        page = self.client.get(self.list_url())
        self.assertContains(page, progress_link(todo, 0, 1), count=1, html=True)
        self.assertNotIn("<img", page.content.decode())

    def test_steps_page_with_no_steps(self):
        shop = self.make_todo(title="Shop")
        response = self.client.get(self.steps_url(todo=shop))
        self.assertInHTML(
            '<ul class="steps"><li>No steps yet.</li></ul>',
            page_without_csrf(response),
            count=1,
        )

    def test_steps_page_of_a_missing_todo_is_404(self):
        response = self.client.get("/999/subtasks/")
        self.assertEqual(response.status_code, 404)

    def test_add_a_step(self):
        response = self.client.post(self.url("subtask_add"), {"title": "Buy sugar"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/{self.cake.pk}/subtasks/")
        sugar = Subtask.objects.get(title="Buy sugar")
        self.assertEqual(sugar.todo, self.cake)
        self.assertFalse(sugar.done)
        self.assertEqual(
            self.step_titles(), ["Buy flour", "Buy eggs", "Bake", "Buy sugar"]
        )

    def test_bad_step_is_not_saved(self):
        too_long = "a" * 201
        cases = [
            ("   ", "This field is required.", ' value="   "'),
            (
                too_long,
                "Ensure this value has at most 200 characters (it has 201).",
                f' value="{too_long}"',
            ),
        ]
        for typed, message, value in cases:
            with self.subTest(typed=typed[:5]):
                response = self.client.post(self.url("subtask_add"), {"title": typed})
                self.assertEqual(response.status_code, 200)
                box = (
                    f'<input type="text" name="title"{value} maxlength="200" required '
                    'aria-invalid="true" aria-describedby="id_title_error" id="id_title" '
                    "autofocus>"
                )
                error = (
                    f'<ul class="errorlist" id="id_title_error"><li>{message}</li></ul>'
                )
                self.assertInHTML(
                    add_step_form(self.cake, box, error),
                    page_without_csrf(response),
                    count=1,
                )
                self.assertEqual(Subtask.objects.count(), 3)

    def test_done_and_undo_a_step(self):
        response = self.client.post(self.url("subtask_done", self.bake), {"done": "1"})
        self.assertEqual(response["Location"], f"/{self.cake.pk}/subtasks/")
        self.bake.refresh_from_db()
        self.assertTrue(self.bake.done)

        response = self.client.post(self.url("subtask_done", self.bake), {"done": "0"})
        self.assertEqual(response["Location"], f"/{self.cake.pk}/subtasks/")
        self.bake.refresh_from_db()
        self.assertFalse(self.bake.done)

    def test_done_posted_twice_stays_done(self):
        for _ in range(2):
            self.client.post(self.url("subtask_done", self.bake), {"done": "1"})
        self.bake.refresh_from_db()
        self.assertTrue(self.bake.done)

    def test_done_needs_a_wanted_state(self):
        for data in [{}, {"done": "yes"}]:
            with self.subTest(data=data):
                response = self.client.post(self.url("subtask_done", self.bake), data)
                self.assertEqual(response.status_code, 400)
                self.bake.refresh_from_db()
                self.assertFalse(self.bake.done)

    def test_steps_and_the_todo_are_separate(self):
        # Every step done: the to-do itself stays open.
        for step in [self.eggs, self.bake]:
            self.client.post(self.url("subtask_done", step), {"done": "1"})
        self.cake.refresh_from_db()
        self.assertFalse(self.cake.done)

        # Done on the to-do does not tick its open step.
        self.client.post(self.url("subtask_done", self.bake), {"done": "0"})
        # After the rebase on repeating (19), this post sends {"done": "1"}.
        self.client.post(reverse("todo_toggle", args=[self.cake.pk]), {"done": "1"})
        self.cake.refresh_from_db()
        self.assertTrue(self.cake.done)
        self.bake.refresh_from_db()
        self.assertFalse(self.bake.done)

    def test_delete_a_step(self):
        response = self.client.post(self.url("subtask_delete", self.bake))
        self.assertEqual(response["Location"], f"/{self.cake.pk}/subtasks/")
        self.assertEqual(self.step_titles(), ["Buy flour", "Buy eggs"])

    def test_step_of_another_todo_is_404(self):
        # Must pass UNCHANGED after accounts (17) and sharing (20).
        shop = self.make_todo(title="Shop")
        before = self.step_states()
        for name, data in [("subtask_done", {"done": "1"}), ("subtask_delete", {})]:
            with self.subTest(name=name):
                response = self.client.post(self.url(name, self.bake, todo=shop), data)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(self.step_states(), before)

    def test_get_cannot_change_steps(self):
        before = self.step_states()
        urls = [
            self.url("subtask_add"),
            self.url("subtask_done", self.bake),
            self.url("subtask_delete", self.bake),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url, {"title": "x", "done": "1"})
                self.assertEqual(response.status_code, 405)
                self.assertEqual(self.step_states(), before)

    def test_step_changes_need_the_csrf_token(self):
        client = self.csrf_client()
        before = self.step_states()
        cases = [
            ("subtask_add", None, {"title": "Buy sugar"}),
            ("subtask_done", self.bake, {"done": "1"}),
            ("subtask_delete", self.bake, {}),
        ]
        for name, step, data in cases:
            with self.subTest(name=name):
                response = client.post(self.url(name, step), data)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.step_states(), before)

    def test_changes_to_a_missing_todo_or_step_are_404(self):
        before = self.step_states()
        huge = "9" * 26  # far too big for the database's integer
        cases = [
            ("/999/subtasks/add/", {"title": "Buy sugar"}),
            (f"/{huge}/subtasks/add/", {"title": "Buy sugar"}),
            (f"/{self.cake.pk}/subtasks/999/done/", {"done": "1"}),
            (f"/{self.cake.pk}/subtasks/{huge}/done/", {"done": "1"}),
            (f"/999/subtasks/{self.bake.pk}/done/", {"done": "1"}),
            (f"/{self.cake.pk}/subtasks/999/delete/", {}),
            (f"/{self.cake.pk}/subtasks/{huge}/delete/", {}),
            (f"/{huge}/subtasks/{self.bake.pk}/delete/", {}),
        ]
        for url, data in cases:
            with self.subTest(url=url):
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(self.step_states(), before)
                self.assertEqual(Todo.objects.count(), 1)

    def test_step_changes_mark_the_todo_edited(self):
        # Owner decision: a change to the steps is an edit of the to-do, so
        # Undo on a repeating to-do keeps a copy whose steps were changed.
        cases = [
            ("subtask_add", None, {"title": "Buy sugar"}),
            ("subtask_done", self.bake, {"done": "1"}),
            ("subtask_done", self.flour, {"done": "0"}),
            ("subtask_delete", self.eggs, {}),
        ]
        for name, step, data in cases:
            with self.subTest(name=name, data=data):
                Todo.objects.filter(pk=self.cake.pk).update(edited=False)
                response = self.client.post(self.url(name, step), data)
                self.assertEqual(response.status_code, 302)
                self.cake.refresh_from_db()
                self.assertTrue(self.cake.edited)

    def test_a_refused_step_change_does_not_mark_the_todo_edited(self):
        for name, step, data in [
            ("subtask_add", None, {"title": "   "}),
            ("subtask_done", self.bake, {"done": "yes"}),
        ]:
            with self.subTest(name=name):
                Todo.objects.filter(pk=self.cake.pk).update(edited=False)
                self.client.post(self.url(name, step), data)
                self.cake.refresh_from_db()
                self.assertFalse(self.cake.edited)

    def test_step_actions_keep_the_list_settings(self):
        query = "?show=active&next=https://evil.example"
        cases = [
            ("subtask_add", None, {"title": "Buy sugar"}),
            ("subtask_done", self.bake, {"done": "1"}),
            ("subtask_delete", self.bake, {}),
        ]
        for name, step, data in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    self.url(name, step, query),
                    {**data, "next": "https://evil.example"},
                )
                self.assertEqual(
                    response["Location"], f"/{self.cake.pk}/subtasks/?show=active"
                )

    def test_links_keep_the_list_settings(self):
        response = self.client.get(self.steps_url("?show=active"))
        actions = page_parts(response).post_actions
        self.assertEqual(len(actions), 7)  # Done and Delete for 3 steps, and Add
        for action in actions:
            self.assertTrue(action.endswith("?show=active"), action)
        self.assertContains(
            response,
            f'<a href="{self.list_url()}?show=active">Back to the list</a>',
            count=1,
            html=True,
        )

        response = self.client.get(f"/{self.cake.pk}/edit/?show=active")
        self.assertContains(
            response,
            f'<a href="/{self.cake.pk}/subtasks/?show=active">Steps</a>',
            count=1,
            html=True,
        )

    def test_list_shows_step_progress(self):
        # The to-do matches the filter, the search and the sort.
        query = "?show=active&q=cake&sort=due"
        response = self.client.get(self.list_url() + query)
        self.assertContains(
            response, progress_link(self.cake, 1, 3, query), count=1, html=True
        )

        # A to-do with no steps: its whole row, so no progress link in it.
        shop = self.make_todo(title="Shop")
        page = page_without_csrf(self.client.get(self.list_url()))
        self.assertInHTML(list_row(shop), page, count=1)
        self.assertInHTML(
            list_row(self.cake, progress_link(self.cake, 1, 3)), page, count=1
        )

    def test_list_queries_do_not_grow_with_rows(self):
        with CaptureQueriesContext(connection) as one_row:
            self.client.get(self.list_url())
        for n in range(5):
            todo = self.make_todo(title=f"Job {n}")
            Subtask.objects.create(todo=todo, title="Step 1", done=True)
            Subtask.objects.create(todo=todo, title="Step 2")
        with CaptureQueriesContext(connection) as six_rows:
            response = self.client.get(self.list_url())
        self.assertEqual(page_parts(response).titles[-1], "Job 4")
        self.assertEqual(len(six_rows), len(one_row))

    def test_pane_shows_the_steps_row(self):
        selected = f"?selected={self.cake.pk}"
        response = self.client.get(self.list_url() + selected)
        created = show_date(timezone.localtime(self.cake.created_at).date())
        pane = pane_element(
            self.cake,
            created=created,
            close_url=self.list_url(),
            steps=(1, 3, f"/{self.cake.pk}/subtasks/{selected}"),
        )
        self.assertContains(response, pane, count=1, html=True)

        # The pane reads the counts the list already has: no extra query.
        with CaptureQueriesContext(connection) as without:
            self.client.get(self.list_url())
        with CaptureQueriesContext(connection) as with_selected:
            self.client.get(self.list_url() + selected)
        self.assertEqual(len(with_selected), len(without))

    def test_pane_of_a_todo_without_steps_has_no_steps_row(self):
        shop = self.make_todo(title="Shop")
        response = self.client.get(self.list_url(query=f"?selected={shop.pk}"))
        created = show_date(timezone.localtime(shop.created_at).date())
        pane = pane_element(shop, created=created, close_url=self.list_url())
        self.assertContains(response, pane, count=1, html=True)

    def test_admin_shows_steps_inline(self):
        admin = get_user_model().objects.create_superuser("admin", None, None)
        self.client.force_login(admin)
        response = self.client.get(
            reverse("admin:todos_todo_change", args=[self.cake.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<input type="hidden" name="subtasks-TOTAL_FORMS" value="3" '
            'id="id_subtasks-TOTAL_FORMS">',
            count=1,
            html=True,
        )
        for i, step in enumerate([self.flour, self.eggs, self.bake]):
            with self.subTest(step=step.title):
                self.assertContains(
                    response,
                    f'<input type="text" name="subtasks-{i}-title" '
                    f'value="{step.title}" class="vTextField" maxlength="200" '
                    f'id="id_subtasks-{i}-title">',
                    count=1,
                    html=True,
                )
