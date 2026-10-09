from django.contrib import admin
from django.test import SimpleTestCase

from todos.admin import TodoAdmin
from todos.forms import NotesField
from todos.models import Todo


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
        form = model_admin.get_form(request=None)
        self.assertIn("repeat", form.base_fields)
        self.assertNotIn("next_todo", form.base_fields)
