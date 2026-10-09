"""Reorder (16): Move up / Move down, in "My order" (?sort=manual)."""

from todos.models import Todo, TodoList
from todos.tests.integration.helpers import (
    ClassCounter,
    LoggedInTestCase,
    autofocus_tags,
    count_elements,
    first_list,
    make_user,
    move_form,
    move_status,
    page_parts,
    row_html,
)

MY_ORDER = "?sort=manual"


class MoveTests(LoggedInTestCase):
    def make(self, title, **fields):
        return self.make_todo(title=title, **fields)

    def move_url(self, todo, query=MY_ORDER):
        return f"/{todo.pk}/move/{query}"

    def post_move(self, todo, direction, query=MY_ORDER):
        data = {} if direction is None else {"direction": direction}
        return self.client.post(self.move_url(todo, query), data)

    def titles(self, query=MY_ORDER, todo_list=None):
        """The titles on the list page, in order, with `query`."""
        response = self.client.get(self.list_url(todo_list, query))
        return page_parts(response).titles

    def positions(self, todo_list=None):
        rows = Todo.objects.filter(todo_list=todo_list or self.todo_list)
        return list(rows.values_list("pk", "position"))

    # Move: new behaviour.

    def test_move_up_swaps_with_the_row_above(self):
        self.make("A")
        self.make("B")
        c = self.make("C")
        response = self.post_move(c, "up")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"/lists/{self.todo_list.pk}/?sort=manual#todo-{c.pk}",
        )
        self.assertEqual(self.titles(), ["A", "C", "B"])

    def test_move_down_swaps_with_the_row_below(self):
        a = self.make("A")
        self.make("B")
        self.post_move(a, "down")
        self.assertEqual(self.titles(), ["B", "A"])

    def test_move_keeps_the_list_query(self):
        a = self.make("A")
        self.make("B")
        response = self.post_move(a, "down", "?show=active&sort=manual")
        self.assertEqual(
            response["Location"],
            f"/lists/{self.todo_list.pk}/?show=active&sort=manual#todo-{a.pk}",
        )

    def test_move_on_a_filtered_page_jumps_over_a_hidden_row(self):
        # On "Active" the completed X is hidden. Completed to-dos go last, so
        # X is made open, placed, then completed: A, X, B in My order.
        self.make("A")
        x = self.make("X")
        b = self.make("B")
        Todo.objects.filter(pk=x.pk).update(done=True)
        x_position = Todo.objects.get(pk=x.pk).position
        self.post_move(b, "up", "?show=active&sort=manual")
        self.assertEqual(self.titles("?show=active&sort=manual"), ["B", "A"])
        self.assertEqual(Todo.objects.get(pk=x.pk).position, x_position)
        rows = Todo.objects.filter(todo_list=self.todo_list).in_my_order()
        self.assertEqual(list(rows.values_list("title", flat=True)), ["B", "X", "A"])

    def test_move_on_a_search_page_jumps_over_a_hidden_row(self):
        self.make("Buy milk")
        self.make("Call home")
        oat = self.make("Buy oat milk")
        self.post_move(oat, "up", "?q=milk&sort=manual")
        self.assertEqual(self.titles(), ["Buy oat milk", "Call home", "Buy milk"])

    def test_move_on_a_tag_page_jumps_over_a_hidden_row(self):
        # Tags (14): on "?tag=home" only the tagged to-dos are shown.
        milk = self.make("Buy milk")
        self.make("Write report")
        bins = self.make("Put out the bins")
        milk.set_tags(["home"])
        bins.set_tags(["home"])
        query = "?sort=manual&tag=home"
        response = self.post_move(bins, "up", query)
        self.assertEqual(
            response["Location"],
            f"/lists/{self.todo_list.pk}/{query}#todo-{bins.pk}",
        )
        self.assertEqual(self.titles(query), ["Put out the bins", "Buy milk"])
        self.assertEqual(
            self.titles(), ["Put out the bins", "Write report", "Buy milk"]
        )

    def test_move_up_on_the_first_row_changes_nothing(self):
        a = self.make("A")
        b = self.make("B")
        before = self.positions()
        self.assertEqual(self.post_move(a, "up").status_code, 302)
        self.assertEqual(self.post_move(b, "down").status_code, 302)
        self.assertEqual(self.positions(), before)

    def test_move_with_a_bad_direction_is_400(self):
        self.make("A")
        b = self.make("B")
        before = self.positions()
        for direction in ["left", "", "UP", None]:
            with self.subTest(direction=direction):
                self.assertEqual(self.post_move(b, direction).status_code, 400)
                self.assertEqual(self.positions(), before)

    def test_move_is_post_only(self):
        a = self.make("A")
        self.make("B")
        before = self.positions()
        response = self.client.get(self.move_url(a), {"direction": "down"})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.positions(), before)

    def test_move_of_a_missing_todo_is_404(self):
        a = self.make("A")
        a.delete()
        self.assertEqual(self.post_move(a, "up").status_code, 404)

    def test_new_todo_goes_last_in_my_order(self):
        self.make("A")
        b = self.make("B")
        self.post_move(b, "up")
        self.client.post(self.add_url(query=MY_ORDER), {"title": "C"})
        self.assertEqual(self.titles(), ["B", "A", "C"])

    def test_editing_a_todo_into_another_list_puts_it_last(self):
        work = TodoList.objects.create(owner=self.user, name="Work")
        self.make_todo(todo_list=work, title="Report")
        self.make_todo(todo_list=work, title="Slides")
        milk = self.make("Buy milk")
        response = self.client.post(
            f"/{milk.pk}/edit/",
            {
                "title": "Buy milk",
                "priority": "2",
                "repeat": "none",
                "todo_list": str(work.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.titles(todo_list=work), ["Report", "Slides", "Buy milk"])
        self.assertEqual(Todo.objects.get(pk=milk.pk).position, 3)

    # Who may move.

    def test_cannot_move_another_persons_todo(self):
        ben = make_user("ben")
        bens_list = first_list(ben)
        Todo.objects.create(todo_list=bens_list, title="Ben 1")
        bens = Todo.objects.create(todo_list=bens_list, title="Ben 2")
        before = list(Todo.objects.values())
        for direction in ["up", "down"]:
            with self.subTest(direction=direction):
                self.assertEqual(self.post_move(bens, direction).status_code, 404)
                self.assertEqual(list(Todo.objects.values()), before)

    def test_a_move_never_changes_another_persons_list(self):
        # Ben's to-dos are added between ana's, with the same numbers.
        ben = make_user("ben")
        bens_list = first_list(ben)
        self.make("A")
        Todo.objects.create(todo_list=bens_list, title="Ben 1")
        b = self.make("B")
        Todo.objects.create(todo_list=bens_list, title="Ben 2")
        before = list(Todo.objects.filter(todo_list=bens_list).values())
        self.post_move(b, "up")
        self.assertEqual(self.titles(), ["B", "A"])
        self.assertEqual(
            list(Todo.objects.filter(todo_list=bens_list).values()), before
        )

    # The buttons.

    def test_move_buttons_in_my_order(self):
        a = self.make("A")
        b = self.make("B")
        c = self.make("C")
        response = self.client.get(self.list_url(query=MY_ORDER))
        for todo, up, down in [(a, False, True), (b, True, True), (c, True, False)]:
            with self.subTest(title=todo.title):
                self.assertInHTML(
                    move_form(todo, MY_ORDER, up=up, down=down),
                    row_html(response, todo),
                    count=1,
                )

    def test_move_buttons_stop_where_the_completed_todos_start(self):
        # Completed to-dos go last: the last open row cannot go down, and the
        # first completed row cannot go up.
        a = self.make("A")
        b = self.make("B")
        x = self.make("X", done=True)
        y = self.make("Y", done=True)
        response = self.client.get(self.list_url(query=MY_ORDER))
        for todo, up, down in [
            (a, False, True),
            (b, True, False),
            (x, False, True),
            (y, True, False),
        ]:
            with self.subTest(title=todo.title):
                self.assertInHTML(
                    move_form(todo, MY_ORDER, up=up, down=down),
                    row_html(response, todo),
                    count=1,
                )

    def test_move_buttons_keep_the_list_query(self):
        a = self.make("A")
        query = "?show=active&sort=manual"
        response = self.client.get(self.list_url(query=query))
        self.assertInHTML(
            move_form(a, query, up=False, down=False), row_html(response, a), count=1
        )

    def test_no_move_buttons_in_other_sorts(self):
        # Protecting: only My order has the buttons.
        a = self.make("A")
        self.make("B")
        for query in [
            "",
            "?sort=created",
            "?sort=due",
            "?sort=priority",
            "?sort=title",
        ]:
            with self.subTest(query=query):
                response = self.client.get(self.list_url(query=query))
                row = row_html(response, a)
                self.assertEqual(ClassCounter(row, "form", "move").count, 0)
                self.assertNotIn("/move/", row)

    def test_a_todo_with_no_position_is_last_in_my_order(self):
        # bulk_create does not call save(): no number. It must not jump to
        # the top (SQLite puts empty values first unless told otherwise).
        self.make("A")
        self.make("B")
        Todo.objects.bulk_create(
            [Todo(todo_list=self.todo_list, owner=self.user, title="No place")]
        )
        self.assertEqual(self.titles(), ["A", "B", "No place"])

    # After a move: the focus and the message.

    def moved_page(self, todo, direction):
        """Press Move on `todo` from My order, and follow the redirect."""
        return self.client.post(
            self.move_url(todo), {"direction": direction}, follow=True
        )

    def test_after_a_move_the_same_button_has_the_focus(self):
        a = self.make("A")
        b = self.make("B")
        c = self.make("C")
        page = self.moved_page(c, "up")
        self.assertEqual(page_parts(page).titles, ["A", "C", "B"])
        for todo, form in [
            (a, move_form(a, MY_ORDER, up=False)),
            (c, move_form(c, MY_ORDER, focus="up")),
            (b, move_form(b, MY_ORDER, down=False)),
        ]:
            with self.subTest(title=todo.title):
                self.assertInHTML(form, row_html(page, todo), count=1)
        self.assertContains(page, move_status("Moved C up (2 of 3)"), html=True)
        self.assertEqual(count_elements(page, "p", "move-status"), 1)

    def test_after_a_move_only_the_button_has_autofocus(self):
        # The add box has autofocus on every other page. A browser focuses
        # the FIRST element with autofocus, so after a move the box must not
        # have it, or the focus would jump back to the top.
        self.make("A")
        b = self.make("B")
        page = self.moved_page(b, "up")
        self.assertEqual(autofocus_tags(page), [("button", "Move B down")])
        # Without a move, the add box has it, as before.
        page = self.client.get(self.list_url(query=MY_ORDER))
        self.assertEqual(autofocus_tags(page), [("input", "New to-do")])

    def test_at_the_top_the_other_button_has_the_focus(self):
        # Moved to the first row: its ↑ is disabled, so ↓ gets the focus.
        self.make("A")
        b = self.make("B")
        page = self.moved_page(b, "up")
        self.assertInHTML(
            move_form(b, MY_ORDER, up=False, focus="down"), row_html(page, b), count=1
        )
        self.assertContains(page, move_status("Moved B up (1 of 2)"), html=True)

    def test_the_message_names_the_title_safely(self):
        self.make("A")
        tea = self.make("<b>Tea & cake</b>")
        page = self.moved_page(tea, "up")
        self.assertContains(
            page, move_status("Moved <b>Tea & cake</b> up (1 of 2)"), html=True
        )

    def test_a_move_that_changes_nothing_says_nothing(self):
        a = self.make("A")
        self.make("B")
        page = self.moved_page(a, "up")
        self.assertEqual(count_elements(page, "p", "move-status"), 0)
        self.assertInHTML(
            move_form(a, MY_ORDER, up=False, focus="down"), row_html(page, a), count=1
        )

    def test_the_focus_and_the_message_are_shown_once(self):
        self.make("A")
        b = self.make("B")
        self.moved_page(b, "up")
        page = self.client.get(self.list_url(query=MY_ORDER))
        self.assertInHTML(move_form(b, MY_ORDER, up=False), row_html(page, b), count=1)
        self.assertEqual(count_elements(page, "p", "move-status"), 0)

    def test_no_focus_on_another_sort_after_a_move(self):
        # The move came from My order, but the next page is "Date added":
        # it has no buttons, so no focus and no message.
        a = self.make("A")
        b = self.make("B")
        self.post_move(b, "up")
        page = self.client.get(self.list_url())
        self.assertNotIn("autofocus", row_html(page, a) + row_html(page, b))
        self.assertEqual(count_elements(page, "p", "move-status"), 0)
