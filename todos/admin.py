from django.contrib import admin
from django.db import models

from .forms import NotesField
from .models import Subtask, Todo


class SubtaskInline(admin.TabularInline):
    """A to-do's steps, as a small table on the to-do's admin page."""

    model = Subtask
    extra = 0
    fields = ["title", "done"]


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "done", "due_date", "priority", "repeat"]
    # Staff see every to-do, of every person, on purpose.
    list_filter = ["owner", "priority", "repeat", "done"]
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
