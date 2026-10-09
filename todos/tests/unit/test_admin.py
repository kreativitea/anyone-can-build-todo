from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase

from todos.admin import TodoAdmin, TodoListAdmin
from todos.forms import NotesField
from todos.models import Todo, TodoList


def staff_request():
    """A request from a superuser, not saved: the admin form asks who is looking."""
    request = RequestFactory().get("/admin/")
    request.user = get_user_model()(is_superuser=True, is_staff=True)
    return request


class TodoAdminTests(SimpleTestCase):
    def test_admin_notes_count_a_line_break_once(self):
        field = TodoAdmin(Todo, admin.site).formfield_for_dbfield(
            Todo._meta.get_field("notes"), request=None
        )
        self.assertIsInstance(field, NotesField)

    def test_admin_shows_repeat_but_never_next_todo(self):
        # Repeating (19): the admin lists and filters by repeat. next_todo is
        # editable=False, so its edit page never shows it.
        model_admin = TodoAdmin(Todo, admin.site)
        self.assertIn("repeat", model_admin.list_display)
        self.assertIn("repeat", model_admin.list_filter)
        form = model_admin.get_form(request=staff_request())
        self.assertIn("repeat", form.base_fields)
        self.assertNotIn("next_todo", form.base_fields)


class TodoListAdminTests(SimpleTestCase):
    def test_list_owner_is_read_only_once_the_list_exists(self):
        # A new owner would leave the to-dos with the old one (the OWNERSHIP
        # rule: Todo.owner is always the list's owner). A new list needs one.
        model_admin = TodoListAdmin(TodoList, admin.site)
        request = staff_request()
        editing = model_admin.get_readonly_fields(request, obj=TodoList(pk=1))
        self.assertIn("owner", editing)
        self.assertNotIn("owner", model_admin.get_readonly_fields(request, obj=None))
