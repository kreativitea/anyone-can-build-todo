"""The form that adds a step (feature 15)."""

from django.test import SimpleTestCase

from todos.forms import SubtaskForm


class SubtaskFormTests(SimpleTestCase):
    def test_step_form(self):
        self.assertEqual(list(SubtaskForm().fields), ["title"])
        self.assertEqual(SubtaskForm().fields["title"].label, "New step")

        form = SubtaskForm({"title": "  Bake  "})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["title"], "Bake")

        self.assertFalse(SubtaskForm({"title": "   "}).is_valid())
