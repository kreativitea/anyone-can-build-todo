"""Lists (13), review: two requests at the same moment.

A TransactionTestCase really commits, like the live site: the database checks
its rules (the unique name, the list a to-do points to) when a change is
committed. A mock puts the other request's change at the worst moment.
"""

from unittest import mock

from django.test import TransactionTestCase

from todos import views
from todos.forms import TodoListForm
from todos.models import Todo, TodoList
from todos.tests.integration.helpers import first_list, make_user


class ListRaceTests(TransactionTestCase):
    def setUp(self):
        self.ana = make_user("ana")
        self.todo_list = first_list(self.ana)
        self.work = TodoList.objects.create(owner=self.ana, name="Work")
        self.client.force_login(self.ana)

    def both_pass_the_name_check(self):
        """Two requests with the same new name both pass clean_name before
        either one saves. The mock lets this request pass, like the second one.
        """
        return mock.patch.object(
            TodoListForm, "clean_name", lambda form: form.cleaned_data["name"]
        )

    def assert_name_error(self, response, name):
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<ul class="errorlist" id="id_name_error">'
            f"<li>You already have a list called &quot;{name}&quot;.</li></ul>",
            count=1,
            html=True,
        )

    def test_new_list_with_a_name_taken_meanwhile_shows_the_form_again(self):
        with self.both_pass_the_name_check():
            response = self.client.post("/lists/new/", {"name": "work"})
        self.assert_name_error(response, "work")
        self.assertEqual(TodoList.objects.filter(owner=self.ana).count(), 2)

    def test_rename_to_a_name_taken_meanwhile_shows_the_form_again(self):
        with self.both_pass_the_name_check():
            response = self.client.post(
                f"/lists/{self.todo_list.pk}/edit/", {"name": "WORK"}
            )
        self.assert_name_error(response, "WORK")
        # The heading keeps the saved name.
        self.assertContains(
            response, "<h1>Rename or delete My to-dos</h1>", count=1, html=True
        )
        self.todo_list.refresh_from_db()
        self.assertEqual(self.todo_list.name, "My to-dos")

    def test_add_to_a_list_deleted_meanwhile_is_404(self):
        real_get_list = views.get_list

        def found_then_deleted(request, list_id):
            found = real_get_list(request, list_id)
            # Another tab deletes the list right after this request found it.
            TodoList.objects.filter(pk=found.pk).delete()
            return found

        with mock.patch.object(views, "get_list", found_then_deleted):
            response = self.client.post(
                f"/lists/{self.work.pk}/add/", {"title": "Write report"}
            )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Todo.objects.exists())
