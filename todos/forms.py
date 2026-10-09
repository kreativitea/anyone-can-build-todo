import re
import unicodedata

from django import forms

from .models import (
    TAG_MAX_LENGTH,
    TAGS_PER_TODO,
    Subtask,
    Todo,
    TodoList,
    clean_tag_name,
    list_name_key,
)

# The tags in the Tags box are split at a comma, or at the Japanese comma "、"
# (NFKC does not change "、"; it does change the wide "，" and small "﹐").
TAG_SEPARATORS = re.compile("[,、]")


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
    # Tags (14): one text box, not a model field (`tags` is the model field).
    # Saved in _save_m2m. max_length refuses a huge post early.
    tag_names = forms.CharField(
        label="Tags",
        required=False,
        max_length=200,
        help_text="separated by commas",
        widget=forms.TextInput(attrs={"placeholder": "home, urgent"}),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # The edit page: the saved tags, in a-b-c order (Tag's ordering).
            names = (tag.name for tag in self.instance.tags.all())
            self.initial["tag_names"] = ", ".join(names)

    def clean_tag_names(self):
        """The Tags box as a list of clean names: no empty ones, no repeats.

        NFKC on the whole box first, so the wide and small commas become ","
        before the split. Too long a name, or too many, is an error (refused,
        never cut: this is saved data).
        """
        text = unicodedata.normalize("NFKC", self.cleaned_data["tag_names"])
        pieces = map(clean_tag_name, TAG_SEPARATORS.split(text))
        names = list(dict.fromkeys(name for name in pieces if name))
        if any(len(name) > TAG_MAX_LENGTH for name in names):
            raise forms.ValidationError(
                f"A tag can be at most {TAG_MAX_LENGTH} characters."
            )
        if len(names) > TAGS_PER_TODO:
            raise forms.ValidationError(f"At most {TAGS_PER_TODO} tags on one to-do.")
        return names

    def _save_m2m(self):
        """Django saves many-to-many data here: at once with save(), or later
        with save_m2m() after save(commit=False). So the tags are saved both ways.
        """
        super()._save_m2m()
        self.instance.set_tags(self.cleaned_data["tag_names"])

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


class TodoListForm(forms.ModelForm):
    """The name of a list, on the "New list" and "Rename or delete" pages.

    `owner` is keyword-only: forgetting it is an error at once. The owner is
    never a field: the view sets it.
    """

    class Meta:
        model = TodoList
        fields = [
            "name",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"autofocus": True}),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    def clean_name(self):
        """One person cannot have two lists with the same name: the same
        `name_key` (NFKC, then casefold), like the database constraint.

        Django skips the database constraint here (`owner` is not a field), so
        the form checks it. The constraint is the safety net.
        """
        name = self.cleaned_data["name"]
        same = TodoList.objects.owned_by(self.owner).filter(
            name_key=list_name_key(name)
        )
        if same.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(self.name_used_message(name))
        return name

    @staticmethod
    def name_used_message(name):
        return f'You already have a list called "{name}".'


class SubtaskForm(forms.ModelForm):
    """The "New step" box on the steps page. Django checks: not empty, at most 200."""

    class Meta:
        model = Subtask
        fields = [
            "title",
        ]
        labels = {
            "title": "New step",
        }
        widgets = {
            # The steps page is for adding steps, so the box is ready to type in.
            "title": forms.TextInput(attrs={"autofocus": True}),
        }


class TodoEditForm(TodoForm):
    """The add form, for a to-do that already exists. Every field of TodoForm is here too,
    and the list it is in (to move it).

    On this page every box has a visible label, so the hidden names and hints go.
    `user` is keyword-only: forgetting it is an error at once.
    """

    class Meta(TodoForm.Meta):
        fields = TodoForm.Meta.fields + ["todo_list"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        # Only this person's lists: the box shows only these, and any other id
        # that is posted is refused ("Select a valid choice").
        self.fields["todo_list"].queryset = TodoList.objects.for_user(user)
        # A to-do is always in a list: no "---------" choice.
        self.fields["todo_list"].empty_label = None
        # A browser always sends the box. A hand-made post without it keeps
        # the to-do where it is, like a missing priority is Medium.
        self.fields["todo_list"].required = False
        # self.fields is this form's own copy. Never change self.base_fields:
        # some of those field objects are shared with TodoForm (the add form).
        for field in self.fields.values():
            field.widget.attrs.pop("aria-label", None)
            field.widget.attrs.pop("placeholder", None)

    def clean_todo_list(self):
        """The chosen list, or (when the post has none) the list it is in now."""
        return self.cleaned_data["todo_list"] or self.instance.todo_list
