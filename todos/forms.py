from django import forms

from .models import Todo


class TodoForm(forms.ModelForm):
    due_date = forms.DateField(
        label="Due date (optional)",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Todo
        fields = ["title", "due_date"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "aria-label": "New to-do",
                    "placeholder": "What needs doing?",
                    "autofocus": True,
                }
            ),
        }
