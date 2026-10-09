from datetime import date

from django.test import SimpleTestCase
from django.utils import translation

from todos import forms
from todos.models import Todo


class EditFormTests(SimpleTestCase):
    def test_edit_form_has_every_field_a_person_can_change(self):
        # Every model field a person may change, read from the model, so a new
        # field feature needs no change here. "done" has its own button.
        expected = {
            field.name
            for field in Todo._meta.get_fields()
            if getattr(field, "editable", False) and not field.auto_created
        } - {"done"}
        self.assertEqual(set(forms.TodoEditForm().fields), expected)

    def test_edit_form_does_not_change_the_add_form(self):
        forms.TodoEditForm()
        add_form = forms.TodoForm()
        expected = {
            "title": {
                "aria-label": "New to-do",
                "placeholder": "What needs doing?",
                "autofocus": True,
                "maxlength": "200",
            },
            # Django moves "type" out of attrs, into widget.input_type.
            "due_date": {},
            "priority": {},
            "notes": {
                "cols": "40",
                "rows": 3,
                "aria-label": "Notes",
                "maxlength": "500",
            },
        }
        self.assertEqual(set(add_form.fields), set(expected))
        for name, attrs in expected.items():
            with self.subTest(field=name):
                self.assertEqual(add_form.fields[name].widget.attrs, attrs)
        self.assertEqual(add_form.fields["due_date"].widget.input_type, "date")

    def test_date_box_shows_iso_date_in_every_language(self):
        todo = Todo(title="Buy milk", due_date=date(2026, 10, 12))
        with translation.override("en-gb"):
            box = str(forms.TodoForm(instance=todo)["due_date"])
        self.assertHTMLEqual(
            box,
            '<input type="date" name="due_date" value="2026-10-12" id="id_due_date">',
        )
