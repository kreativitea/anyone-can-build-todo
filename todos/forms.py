from django import forms

from .models import Todo


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
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "aria-label": "New to-do",
                    "placeholder": "What needs doing?",
                    "autofocus": True,
                }
            ),
        }
