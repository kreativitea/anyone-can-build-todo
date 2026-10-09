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
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
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
    # Like priority: a missing or empty repeat is "none". The check "a
    # repeating to-do needs a due date" is in Todo.clean(), so the add form,
    # the edit page and the admin all get it.
    repeat = forms.TypedChoiceField(
        label="Repeats",
        choices=Todo.Repeat.choices,
        required=False,
        empty_value=Todo.Repeat.NONE,
        initial=Todo.Repeat.NONE,
    )

    class Meta:
        model = Todo
        fields = [
            "title",
            "due_date",
            "priority",
            "notes",
            "repeat",
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

    def save(self, commit=True):
        """Save, and remember the due date's day for a monthly repeat.

        Only when the to-do is new, or its due date or repeat changed: fixing
        a typo in a copy due 28 Feb must not move "the 31st" to the 28th.
        """
        # self.errors runs the checks first: they put the new values in
        # self.instance. With errors, super().save() refuses, as always.
        changed = {"due_date", "repeat"} & set(self.changed_data)
        if not self.errors and (self.instance._state.adding or changed):
            due = self.instance.due_date
            self.instance.repeat_day = due.day if due else None
        return super().save(commit)

    def notes_box_open(self):
        """Open the folded notes box when there are notes to see, or an error about them."""
        if self["notes"].errors:
            return True
        return bool(getattr(self, "cleaned_data", {}).get("notes"))


class TodoEditForm(TodoForm):
    """The add form, for a to-do that already exists. Every field of TodoForm is here too.

    On this page every box has a visible label, so the hidden names and hints go.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields is this form's own copy. Never change self.base_fields:
        # some of those field objects are shared with TodoForm (the add form).
        for field in self.fields.values():
            field.widget.attrs.pop("aria-label", None)
            field.widget.attrs.pop("placeholder", None)
