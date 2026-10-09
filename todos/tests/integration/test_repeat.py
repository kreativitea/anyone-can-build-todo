"""Repeating to-dos (feature 19), through the test client.

Done and Undo post the state the person wants: done=1 or done=0.
"""

from datetime import date

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from todos.models import Subtask, Todo
from todos.tests.integration.helpers import (
    page_forms,
    page_without_csrf,
    pane_element,
    show_date,
    title_element,
    toggle_form,
)

MONDAY = date(2026, 10, 12)
NEXT_MONDAY = date(2026, 10, 19)
NEEDS_A_DATE = "A repeating to-do needs a due date."


def done(todo, query=""):
    """The address of a to-do's Done/Undo form."""
    return reverse("todo_toggle", args=[todo.pk]) + query


class WantedStateTests(TestCase):
    """Done and Undo for EVERY to-do (also one that does not repeat): the
    button sends the state the person wants, so a second press changes nothing.
    """

    def setUp(self):
        self.milk = Todo.objects.create(title="Buy milk", due_date=MONDAY)

    def press(self, todo, wanted):
        """Press Done (wanted="1") or Undo (wanted="0") on `todo`."""
        return self.client.post(done(todo), {"done": wanted})

    def test_done_from_an_old_tab_keeps_it_done(self):
        # A second Done (a double click, or a page opened before the first
        # Done) must not flip it back to open.
        self.press(self.milk, "1")
        self.press(self.milk, "1")
        self.milk.refresh_from_db()
        self.assertTrue(self.milk.done)

    def test_undo_on_an_open_todo_does_nothing(self):
        response = self.press(self.milk, "0")
        self.assertEqual(response.status_code, 302)
        self.milk.refresh_from_db()
        self.assertFalse(self.milk.done)
        self.assertEqual(Todo.objects.count(), 1)

    def test_done_without_a_wanted_state_is_400(self):
        for data in [{}, {"done": "2"}, {"done": "yes"}]:
            with self.subTest(data=data):
                response = self.client.post(done(self.milk), data)
                self.assertEqual(response.status_code, 400)
                self.milk.refresh_from_db()
                self.assertFalse(self.milk.done)

    def test_done_on_a_todo_that_does_not_repeat_makes_no_copy(self):
        # Protecting: this already works, and must keep working.
        self.press(self.milk, "1")
        self.milk.refresh_from_db()
        self.assertTrue(self.milk.done)
        self.assertEqual(Todo.objects.count(), 1)


class DoneAndUndoTests(TestCase):
    def setUp(self):
        self.bins = Todo.objects.create(
            title="Bins",
            due_date=MONDAY,
            repeat="weekly",
            priority=Todo.Priority.HIGH,
            notes="blue bag",
        )

    def press(self, todo, wanted, query=""):
        """Press Done (wanted="1") or Undo (wanted="0") on `todo`."""
        return self.client.post(done(todo, query), {"done": wanted})

    def open_todos(self):
        return list(Todo.objects.filter(done=False))

    def test_done_on_a_weekly_todo_makes_the_next_one(self):
        response = self.press(self.bins, "1")
        self.assertEqual(response.status_code, 302)
        self.bins.refresh_from_db()
        self.assertTrue(self.bins.done)
        [copy] = self.open_todos()
        self.assertEqual(
            (copy.title, copy.due_date, copy.repeat, copy.priority, copy.notes),
            ("Bins", NEXT_MONDAY, "weekly", Todo.Priority.HIGH, "blue bag"),
        )
        self.assertEqual(self.bins.next_todo, copy)

    def test_done_posted_twice_makes_one_copy(self):
        # A double click, or Done pressed again in an old tab.
        self.press(self.bins, "1")
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        self.assertTrue(self.bins.done)
        self.assertEqual(Todo.objects.count(), 2)
        [copy] = self.open_todos()
        self.assertEqual(copy.due_date, NEXT_MONDAY)

    def test_undo_deletes_the_untouched_open_copy(self):
        self.press(self.bins, "1")
        self.press(self.bins, "0")
        self.assertEqual(list(Todo.objects.all()), [self.bins])
        self.bins.refresh_from_db()
        self.assertFalse(self.bins.done)
        self.assertEqual(self.bins.due_date, MONDAY)
        self.assertIsNone(self.bins.next_todo)

    def test_done_undo_done_makes_one_open_copy(self):
        self.press(self.bins, "1")
        self.press(self.bins, "0")
        self.press(self.bins, "1")
        [copy] = self.open_todos()
        self.assertEqual(copy.due_date, NEXT_MONDAY)
        self.assertEqual(list(Todo.objects.filter(done=True)), [self.bins])

    def test_undo_keeps_an_edited_copy(self):
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        copy = self.bins.next_todo
        self.client.post(
            reverse("todo_edit", args=[copy.pk]),
            {
                "title": "Bins and recycling",
                "due_date": "2026-10-19",
                "priority": "3",
                "notes": "blue bag",
                "repeat": "weekly",
            },
        )
        self.press(self.bins, "0")
        copy.refresh_from_db()
        self.assertEqual(copy.title, "Bins and recycling")
        self.bins.refresh_from_db()
        self.assertFalse(self.bins.done)
        self.assertEqual(self.bins.next_todo, copy)
        # The link is kept, so Done again makes no new to-do.
        self.press(self.bins, "1")
        self.assertEqual(Todo.objects.count(), 2)

    def test_undo_in_a_chain_keeps_the_completed_copy(self):
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        second = self.bins.next_todo
        self.press(second, "1")
        second.refresh_from_db()
        third = second.next_todo
        self.press(self.bins, "0")
        self.bins.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertFalse(self.bins.done)
        self.assertTrue(second.done)
        self.assertFalse(third.done)
        self.assertEqual(self.bins.next_todo, second)
        self.press(self.bins, "1")
        self.assertEqual(Todo.objects.count(), 3)

    def test_undo_after_the_copy_was_deleted(self):
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        self.client.post(reverse("todo_delete", args=[self.bins.next_todo.pk]))
        response = self.press(self.bins, "0")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(Todo.objects.all()), [self.bins])
        self.bins.refresh_from_db()
        self.assertFalse(self.bins.done)

    def test_two_requests_at_once_make_one_copy(self):
        # Two Python objects, read at the same moment, like two requests.
        a = Todo.objects.get(pk=self.bins.pk)
        b = Todo.objects.get(pk=self.bins.pk)
        a.set_done(True)
        b.set_done(True)
        self.assertEqual(Todo.objects.count(), 2)
        self.assertEqual(Todo.objects.filter(done=True).count(), 1)
        self.assertEqual(len(self.open_todos()), 1)

    def test_done_keeps_the_filter(self):
        response = self.client.post(
            done(self.bins, "?show=active"), {"done": "1"}, follow=True
        )
        self.assertEqual(response.redirect_chain, [("/?show=active", 302)])
        [copy] = self.open_todos()
        element = title_element(copy, "?show=active", repeat="Every week")
        self.assertContains(response, element, count=1, html=True)

    def test_delete_completed_keeps_the_next_copy(self):
        self.press(self.bins, "1")
        self.client.post(reverse("todo_delete_completed"), {"ids": [self.bins.pk]})
        [copy] = Todo.objects.all()
        self.assertFalse(copy.done)
        self.assertEqual(copy.due_date, NEXT_MONDAY)

    def admin_save(self, todo, **changes):
        """Save `todo` on its admin change page, with `changes` to its fields."""
        admin_user = User.objects.create_superuser("admin", "admin@example.test")
        self.client.force_login(admin_user)
        data = {
            "title": todo.title,
            "due_date": todo.due_date.isoformat() if todo.due_date else "",
            "priority": str(todo.priority),
            "notes": todo.notes,
            "repeat": todo.repeat,
            "_save": "Save",
        }
        # The steps inline (15): the admin page always sends its management
        # form, and each step the to-do has, unchanged.
        steps = list(todo.subtasks.all())
        data["subtasks-TOTAL_FORMS"] = str(len(steps))
        data["subtasks-INITIAL_FORMS"] = str(len(steps))
        for i, step in enumerate(steps):
            data[f"subtasks-{i}-id"] = str(step.pk)
            data[f"subtasks-{i}-todo"] = str(todo.pk)
            data[f"subtasks-{i}-title"] = step.title
            if step.done:
                data[f"subtasks-{i}-done"] = "on"
        if todo.done:
            data["done"] = "on"
        data.update(changes)
        if data.get("done") is False:
            del data["done"]
        response = self.client.post(
            reverse("admin:todos_todo_change", args=[todo.pk]), data
        )
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        return response

    def edit(self, todo, **changes):
        """Save `todo` on its edit page, sending what the page's form sends."""
        page = self.client.get(reverse("todo_edit", args=[todo.pk]))
        (form,) = [f for f in page_forms(page) if f.method == "post"]
        response = self.client.post(form.action, form.data(**changes))
        self.assertEqual(response.status_code, 302)
        return response

    def test_admin_done_makes_no_copy(self):
        # Owner decision: only the Done button makes the next copy.
        self.admin_save(self.bins, done="on")
        self.bins.refresh_from_db()
        self.assertTrue(self.bins.done)
        self.assertEqual(Todo.objects.count(), 1)

    # Review fixes: Undo decides with the copy's own state, never by
    # building the copy again from the original.

    def test_undo_after_the_original_stopped_repeating(self):
        # Done, then the completed original is set to "Does not repeat".
        # Undo used to build the copy again with repeat "none": a 500 error.
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        self.edit(self.bins, repeat="none")
        response = self.press(self.bins, "0")
        self.assertEqual(response.status_code, 302)
        self.bins.refresh_from_db()
        self.assertFalse(self.bins.done)
        # The copy was not touched, so Undo deletes it.
        self.assertEqual(list(Todo.objects.all()), [self.bins])

    def test_undo_after_the_admin_stopped_the_repeat(self):
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        self.admin_save(self.bins, repeat="none")
        response = self.press(self.bins, "0")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(Todo.objects.all()), [self.bins])

    def test_undo_after_fixing_a_typo_in_the_original_deletes_the_copy(self):
        # The copy has the old title, but nobody touched the COPY: it goes.
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        self.edit(self.bins, title="Bins!")
        self.press(self.bins, "0")
        self.assertEqual(list(Todo.objects.all()), [self.bins])

    def test_edit_and_admin_save_mark_a_todo_edited(self):
        self.edit(self.bins)
        self.bins.refresh_from_db()
        self.assertTrue(self.bins.edited)
        milk = Todo.objects.create(title="Buy milk")
        self.admin_save(milk)
        milk.refresh_from_db()
        self.assertTrue(milk.edited)

    def test_undo_keeps_a_copy_completed_in_the_admin(self):
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        copy = self.bins.next_todo
        self.admin_save(copy, done="on")
        self.press(self.bins, "0")
        copy.refresh_from_db()
        self.assertTrue(copy.done)
        self.assertIsNone(copy.next_todo)  # the admin made no copy of its own

    def test_undo_keeps_a_completed_copy(self):
        # Only the "copy is open" rule protects this copy: it has no copy of
        # its own, and nobody edited it (completed by a plain update).
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        copy = self.bins.next_todo
        Todo.objects.filter(pk=copy.pk).update(done=True)
        self.press(self.bins, "0")
        copy.refresh_from_db()
        self.assertTrue(copy.done)
        self.assertFalse(copy.edited)

    def test_undo_keeps_an_open_copy_that_has_its_own_copy(self):
        # Monday -> Done -> Tuesday -> Done -> Wednesday, edit Wednesday,
        # Undo Tuesday (Wednesday is kept: edited). Now Tuesday is open and
        # untouched, but it has its own copy: Undo on Monday must keep it.
        self.press(self.bins, "1")
        self.bins.refresh_from_db()
        second = self.bins.next_todo
        self.press(second, "1")
        second.refresh_from_db()
        third = second.next_todo
        self.edit(third, title="Bins and recycling")
        self.press(second, "0")
        second.refresh_from_db()
        self.assertFalse(second.done)
        self.assertFalse(second.edited)
        self.assertEqual(second.next_todo, third)
        self.press(self.bins, "0")
        self.assertEqual(Todo.objects.count(), 3)
        second.refresh_from_db()
        self.assertEqual(second.next_todo, third)

    def test_done_in_year_9999_makes_no_copy(self):
        # The next date would be after 31 Dec 9999, the last date Python has.
        far = Todo.objects.create(
            title="Far away", due_date=date(9999, 12, 28), repeat="weekly"
        )
        response = self.press(far, "1")
        self.assertEqual(response.status_code, 302)
        far.refresh_from_db()
        self.assertTrue(far.done)
        self.assertIsNone(far.next_todo)
        self.assertFalse(Todo.objects.filter(title="Far away", done=False).exists())


class MonthlyDayTests(TestCase):
    """Monthly remembers the day the person chose (owner decision)."""

    def press_done(self, todo):
        response = self.client.post(done(todo), {"done": "1"})
        self.assertEqual(response.status_code, 302)
        todo.refresh_from_db()
        return todo.next_todo

    def test_monthly_from_the_30th_never_drifts(self):
        self.client.post(
            reverse("todo_add"),
            {"title": "Pay rent", "due_date": "2027-01-30", "repeat": "monthly"},
        )
        todo = Todo.objects.get()
        dates = []
        for _ in range(12):
            todo = self.press_done(todo)
            dates.append(todo.due_date)
        expected = [date(2027, 2, 28)]
        expected += [date(2027, month, 30) for month in range(3, 13)]
        expected += [date(2028, 1, 30)]
        self.assertEqual(dates, expected)

    def test_editing_the_copys_date_moves_the_day(self):
        self.client.post(
            reverse("todo_add"),
            {"title": "Pay rent", "due_date": "2027-01-31", "repeat": "monthly"},
        )
        copy = self.press_done(Todo.objects.get())
        self.assertEqual(copy.due_date, date(2027, 2, 28))
        page = self.client.get(reverse("todo_edit", args=[copy.pk]))
        (form,) = [f for f in page_forms(page) if f.method == "post"]
        self.client.post(form.action, form.data(due_date="2027-02-27"))
        self.assertEqual(self.press_done(copy).due_date, date(2027, 3, 27))

    def test_fixing_the_copys_title_keeps_the_day(self):
        self.client.post(
            reverse("todo_add"),
            {"title": "Pay rnet", "due_date": "2027-01-31", "repeat": "monthly"},
        )
        copy = self.press_done(Todo.objects.get())
        page = self.client.get(reverse("todo_edit", args=[copy.pk]))
        (form,) = [f for f in page_forms(page) if f.method == "post"]
        self.client.post(form.action, form.data(title="Pay rent"))
        self.assertEqual(self.press_done(copy).due_date, date(2027, 3, 31))


class RepeatFormTests(TestCase):
    def test_add_a_weekly_todo(self):
        self.client.post(
            reverse("todo_add"),
            {"title": "Bins", "due_date": "2026-10-12", "repeat": "weekly"},
        )
        self.assertEqual(Todo.objects.get().repeat, "weekly")

    def test_add_without_repeat_does_not_repeat(self):
        self.client.post(reverse("todo_add"), {"title": "Buy milk"})
        self.assertEqual(Todo.objects.get().repeat, "none")

    def test_repeat_without_due_date_is_rejected(self):
        response = self.client.post(
            reverse("todo_add"), {"title": "Water plants", "repeat": "daily"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Todo.objects.exists())
        # The error is right before the Repeats label.
        self.assertInHTML(
            f'<ul class="errorlist" id="id_repeat_error"><li>{NEEDS_A_DATE}</li></ul>'
            '<label for="id_repeat">Repeats:</label>',
            page_without_csrf(response),
            count=1,
        )
        [add] = [f for f in page_forms(response) if f.action == reverse("todo_add")]
        self.assertEqual(add.fields["title"], ["Water plants"])
        self.assertEqual(add.fields["repeat"], ["daily"])

    def test_unknown_repeat_is_rejected(self):
        response = self.client.post(
            reverse("todo_add"),
            {"title": "Bins", "due_date": "2026-10-12", "repeat": "yearly"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Todo.objects.exists())

    def test_list_page_has_a_repeats_box(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(
            response, '<label for="id_repeat">Repeats:</label>', count=1, html=True
        )
        self.assertContains(
            response,
            '<select name="repeat" id="id_repeat">'
            '<option value="none" selected>Does not repeat</option>'
            '<option value="daily">Every day</option>'
            '<option value="weekly">Every week</option>'
            '<option value="monthly">Every month</option>'
            "</select>",
            count=1,
            html=True,
        )

    def test_add_button_has_its_own_row(self):
        # So it does not look like a part of the Repeats box.
        page = page_without_csrf(self.client.get(reverse("todo_list")))
        self.assertInHTML(
            '<div class="add-actions"><button type="submit">Add</button></div>',
            page,
            count=1,
        )

    def test_done_and_undo_buttons_send_the_wanted_state(self):
        milk = Todo.objects.create(title="Buy milk")
        home = Todo.objects.create(title="Call home", done=True)
        page = page_without_csrf(self.client.get(reverse("todo_list")))
        self.assertInHTML(toggle_form(milk), page, count=1)
        self.assertInHTML(toggle_form(home, done=True), page, count=1)
        self.assertIn('<input type="hidden" name="done" value="1">', toggle_form(milk))
        self.assertIn(
            '<input type="hidden" name="done" value="0">', toggle_form(home, True)
        )

    def test_open_repeating_todo_shows_its_repeat(self):
        bins = Todo.objects.create(title="Bins", due_date=MONDAY, repeat="weekly")
        response = self.client.get(reverse("todo_list"))
        element = title_element(bins, repeat="Every week")
        self.assertIn('<span class="repeat">Every week</span>', element)
        self.assertContains(response, element, count=1, html=True)

    def test_completed_repeating_todo_does_not_show_repeat(self):
        bins = Todo.objects.create(
            title="Bins", due_date=MONDAY, repeat="weekly", done=True
        )
        response = self.client.get(reverse("todo_list"))
        # The whole title span of that row, exactly: no repeat span in it.
        self.assertContains(response, title_element(bins), count=1, html=True)

    def test_edit_the_copys_due_date(self):
        bins = Todo.objects.create(title="Bins", due_date=MONDAY, repeat="weekly")
        self.client.post(done(bins), {"done": "1"})
        bins.refresh_from_db()
        copy = bins.next_todo
        # Send exactly what the edit page's form sends, with a new date.
        page = self.client.get(reverse("todo_edit", args=[copy.pk]))
        (form,) = [f for f in page_forms(page) if f.method == "post"]
        self.assertEqual(form.fields["repeat"], ["weekly"])
        response = self.client.post(form.action, form.data(due_date="2026-10-14"))
        self.assertEqual(response.status_code, 302)
        copy.refresh_from_db()
        self.assertEqual(copy.due_date, date(2026, 10, 14))
        self.assertEqual(copy.repeat, "weekly")
        self.assertEqual(Todo.objects.count(), 2)
        bins.refresh_from_db()
        self.assertTrue(bins.done)
        self.assertEqual(bins.next_todo, copy)

    def test_edit_page_shows_the_saved_repeat(self):
        rent = Todo.objects.create(
            title="Pay rent", due_date=date(2026, 10, 31), repeat="monthly"
        )
        response = self.client.get(reverse("todo_edit", args=[rent.pk]))
        self.assertContains(
            response,
            '<option value="monthly" selected>Every month</option>',
            count=1,
            html=True,
        )

    def test_edit_removing_the_date_of_a_repeating_todo_is_rejected(self):
        bins = Todo.objects.create(title="Bins", due_date=MONDAY, repeat="weekly")
        response = self.client.post(
            reverse("todo_edit", args=[bins.pk]),
            {"title": "Bins", "due_date": "", "priority": "2", "repeat": "weekly"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<ul class="errorlist" id="id_repeat_error"><li>{NEEDS_A_DATE}</li></ul>',
            count=1,
            html=True,
        )
        bins.refresh_from_db()
        self.assertEqual(bins.due_date, MONDAY)


class RepeatPaneTests(TestCase):
    """The details pane shows a Repeats row, only for a to-do that repeats."""

    def created(self, todo):
        return show_date(timezone.localtime(todo.created_at).date())

    def test_pane_shows_the_repeat(self):
        bins = Todo.objects.create(title="Bins", due_date=MONDAY, repeat="weekly")
        response = self.client.get(f"/?selected={bins.pk}")
        pane = pane_element(
            bins,
            due="12 Oct 2026",
            repeats="Every week",
            created=self.created(bins),
            close_url="/",
        )
        self.assertIn("<dt>Repeats</dt><dd>Every week</dd>", pane)
        self.assertContains(response, pane, count=1, html=True)

    def test_pane_has_no_repeats_row_for_a_todo_that_does_not_repeat(self):
        milk = Todo.objects.create(title="Buy milk", due_date=MONDAY)
        response = self.client.get(f"/?selected={milk.pk}")
        # The whole pane, exactly: it has no Repeats row.
        pane = pane_element(
            milk, due="12 Oct 2026", created=self.created(milk), close_url="/"
        )
        self.assertContains(response, pane, count=1, html=True)

    def test_pane_of_a_completed_repeating_todo_still_shows_the_repeat(self):
        # The pane shows every field. The list hides the repeat of a completed
        # to-do (its next copy repeats now), but the field is still saved.
        bins = Todo.objects.create(
            title="Bins", due_date=MONDAY, repeat="weekly", done=True
        )
        response = self.client.get(f"/?selected={bins.pk}")
        pane = pane_element(
            bins,
            status="Completed",
            due="12 Oct 2026",
            repeats="Every week",
            created=self.created(bins),
            close_url="/",
        )
        self.assertContains(response, pane, count=1, html=True)


class RepeatingStepsTests(TestCase):
    """Steps (15) and repeating (19): Done copies the steps, all not done.

    Owner decisions: the steps come back with the next copy; a change to a
    copy's steps counts as an edit, so Undo keeps that copy.
    """

    def make_clean(self, steps=(("Kitchen", True), ("Floor", False))):
        clean = Todo.objects.create(
            title="Weekly clean", due_date=MONDAY, repeat="weekly"
        )
        for title, is_done in steps:
            Subtask.objects.create(todo=clean, title=title, done=is_done)
        return clean

    def press(self, todo, wanted):
        response = self.client.post(done(todo), {"done": wanted})
        self.assertEqual(response.status_code, 302)
        todo.refresh_from_db()

    def steps(self, todo):
        return list(todo.subtasks.values_list("title", "done"))

    def test_done_copies_the_steps_not_done(self):
        clean = self.make_clean()
        self.press(clean, "1")
        copy = clean.next_todo
        self.assertIsNotNone(copy)
        self.assertEqual(self.steps(copy), [("Kitchen", False), ("Floor", False)])
        # The completed one keeps its steps as they were: its history.
        self.assertEqual(self.steps(clean), [("Kitchen", True), ("Floor", False)])

    def test_done_copies_all_steps_in_one_query(self):
        counts = []
        for n in [2, 5]:
            clean = self.make_clean([(f"Room {i}", False) for i in range(n)])
            with CaptureQueriesContext(connection) as queries:
                self.press(clean, "1")
            counts.append(len(queries))
            self.assertEqual(clean.next_todo.subtasks.count(), n)
        self.assertEqual(counts[0], counts[1])

    def test_undo_deletes_a_copy_with_untouched_steps(self):
        clean = self.make_clean()
        self.press(clean, "1")
        self.press(clean, "0")
        self.assertEqual(list(Todo.objects.all()), [clean])
        self.assertFalse(clean.done)
        self.assertEqual(self.steps(clean), [("Kitchen", True), ("Floor", False)])
        # The copied steps went with the copy (CASCADE).
        self.assertEqual(Subtask.objects.count(), 2)

    def test_undo_keeps_a_copy_whose_steps_changed(self):
        def tick_floor(copy):
            floor = copy.subtasks.get(title="Floor")
            return reverse("subtask_done", args=[copy.pk, floor.pk]), {"done": "1"}

        def add_bath(copy):
            return reverse("subtask_add", args=[copy.pk]), {"title": "Bath"}

        def delete_kitchen(copy):
            kitchen = copy.subtasks.get(title="Kitchen")
            return reverse("subtask_delete", args=[copy.pk, kitchen.pk]), {}

        cases = [
            (tick_floor, [("Kitchen", False), ("Floor", True)]),
            (add_bath, [("Kitchen", False), ("Floor", False), ("Bath", False)]),
            (delete_kitchen, [("Floor", False)]),
        ]
        for change, left in cases:
            with self.subTest(change=change.__name__):
                Todo.objects.all().delete()
                clean = self.make_clean()
                self.press(clean, "1")
                copy = clean.next_todo
                url, data = change(copy)
                self.assertEqual(self.client.post(url, data).status_code, 302)

                self.press(clean, "0")
                self.assertFalse(clean.done)
                self.assertTrue(Todo.objects.filter(pk=copy.pk).exists())
                self.assertEqual(self.steps(copy), left)

                # Done again on the old one makes no third to-do.
                self.press(clean, "1")
                self.assertEqual(Todo.objects.count(), 2)

    def test_done_on_a_todo_without_steps_copies_none(self):
        clean = self.make_clean(steps=())
        self.press(clean, "1")
        self.assertEqual(self.steps(clean.next_todo), [])
        self.press(clean, "0")
        self.assertEqual(list(Todo.objects.all()), [clean])
