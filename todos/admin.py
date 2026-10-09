from django.contrib import admin
from django.db import models

from .forms import NotesField
from .models import Subtask, Todo, TodoList


class SubtaskInline(admin.TabularInline):
    """A to-do's steps, as a small table on the to-do's admin page."""

    model = Subtask
    extra = 0
    fields = ["title", "done"]


@admin.register(TodoList)
class TodoListAdmin(admin.ModelAdmin):
    # Staff see every list, of every person, on purpose.
    list_display = ["name", "owner", "created_at"]
    list_filter = ["owner"]

    def get_readonly_fields(self, request, obj=None):
        # A new list needs an owner. Once it exists, a new owner would leave
        # its to-dos with the old one (Todo.owner is always the list's owner).
        if obj is not None:
            return ["owner"]
        return []


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "todo_list",
        "owner",
        "done",
        "due_date",
        "priority",
        "repeat",
    ]
    # Staff see every to-do, of every person, on purpose.
    list_filter = ["owner", "priority", "repeat", "done"]
    # The owner always follows the list (Todo.save): choose the list instead.
    readonly_fields = ["owner"]
    # Ticking "done" here makes no next copy: only the Done button does.
    # Notes are the only TextField: count a line break as one character, like our form.
    formfield_overrides = {models.TextField: {"form_class": NotesField}}

    def save_model(self, request, obj, form, change):
        # Like the edit page: Undo never deletes a to-do a person edited.
        if change:
            obj.edited = True
        super().save_model(request, obj, form, change)

    # A step is always seen with its to-do, so Subtask is not registered alone.
    inlines = [SubtaskInline]
