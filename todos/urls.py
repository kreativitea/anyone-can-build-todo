from django.urls import path

from . import views

urlpatterns = [
    # `/` only sends the browser to the person's first list.
    path("", views.home, name="home"),
    path("lists/<int:list_id>/", views.todo_list, name="todo_list"),
    path("lists/<int:list_id>/add/", views.todo_add, name="todo_add"),
    path(
        "lists/<int:list_id>/delete-completed/",
        views.todo_delete_completed,
        name="todo_delete_completed",
    ),
    path("<int:pk>/toggle/", views.todo_toggle, name="todo_toggle"),
    path("<int:pk>/edit/", views.todo_edit, name="todo_edit"),
    path("<int:pk>/delete/", views.todo_delete, name="todo_delete"),
    path("<int:pk>/subtasks/", views.subtask_list, name="subtask_list"),
    path("<int:pk>/subtasks/add/", views.subtask_add, name="subtask_add"),
    path(
        "<int:pk>/subtasks/<int:subtask_pk>/done/",
        views.subtask_done,
        name="subtask_done",
    ),
    path(
        "<int:pk>/subtasks/<int:subtask_pk>/delete/",
        views.subtask_delete,
        name="subtask_delete",
    ),
]
