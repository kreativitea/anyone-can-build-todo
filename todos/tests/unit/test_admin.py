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
