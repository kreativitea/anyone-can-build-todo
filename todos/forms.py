from django import forms

from .models import Todo


class NotesField(forms.CharField):
    """A text field that counts a line break as one character, like the browser does.

    A browser sends a line break as "\\r\\n" (2 characters), but its maxlength counts
    it as 1. to_python runs before the length check, so we change "\\r\\n" to "\\n" here.
    """

    def to_python(self, value):
        value = super().to_python(value)
        return value.replace("\r\n", "\n").replace("\r", "\n")


class TodoForm(forms.ModelForm):
    due_date = forms.DateField(
        label="Due date (optional)",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    # Written by hand: the box Django would make is required, and a post with
    # only a title must still work. A missing or empty priority is Medium.
    # `initial` is needed: a new form does not read the model's default, and
    # without it the browser would send the first option, High.
    priority = forms.TypedChoiceField(
        label="Priority",
        choices=Todo.Priority.choices,
        coerce=int,
        required=False,
        empty_value=Todo.Priority.MEDIUM,
        initial=Todo.Priority.MEDIUM,
    )

    class Meta:
        model = Todo
        fields = [
            "title",
            "due_date",
            "priority",
            "notes",
        ]
        field_classes = {"notes": NotesField}
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "aria-label": "New to-do",
                    "placeholder": "What needs doing?",
                    "autofocus": True,
                }
            ),
            "notes": forms.Textarea(attrs={"rows": 3, "aria-label": "Notes"}),
        }

    def notes_box_open(self):
        """Open the folded notes box when there are notes to see, or an error about them."""
        if self["notes"].errors:
            return True
        return bool(getattr(self, "cleaned_data", {}).get("notes"))
