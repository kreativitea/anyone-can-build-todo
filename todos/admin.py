from django.contrib import admin
from django.db import models

from .forms import NotesField
from .models import Todo


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ["title", "done", "due_date", "priority", "repeat"]
    list_filter = ["priority", "repeat", "done"]
    # Ticking "done" here makes no next copy: only the Done button does.
    # Notes are the only TextField: count a line break as one character, like our form.
    formfield_overrides = {models.TextField: {"form_class": NotesField}}
