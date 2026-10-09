from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models, transaction
from django.db.models import Count, Q
from django.utils import timezone

from . import repeat as rp

# The longest notes a to-do may have. The form gets it from max_length.
NOTES_LIMIT = 500


class TodoQuerySet(models.QuerySet):
    def remaining(self):
        """The to-dos that are not done yet."""
        return self.filter(done=False)

    def completed(self):
        """The to-dos that are done."""
        return self.filter(done=True)

    def with_subtask_progress(self):
        """Each to-do with its number of steps, and of done steps, in the same query.

        distinct=True counts each step once, even when a later JOIN (like tags)
        puts the same step on two lines.
        """
        return self.annotate(
            subtask_count=Count("subtasks", distinct=True),
            subtask_done_count=Count(
                "subtasks", filter=Q(subtasks__done=True), distinct=True
            ),
        )


class Todo(models.Model):
    class Priority(models.IntegerChoices):
        # A number, so the database sorts it in the right order (High first
        # with "-priority"). Write Todo.Priority.HIGH in code, not 3.
        HIGH = 3, "High"
        MEDIUM = 2, "Medium"
        LOW = 1, "Low"

    class Repeat(models.TextChoices):
        # The database keeps the short word; the page shows the words after it.
        NONE = rp.NONE, "Does not repeat"
        DAILY = rp.DAILY, "Every day"
        WEEKLY = rp.WEEKLY, "Every week"
        MONTHLY = rp.MONTHLY, "Every month"

    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    notes = models.TextField(
        blank=True,
        default="",
        db_default="",
        max_length=NOTES_LIMIT,
        validators=[MaxLengthValidator(NOTES_LIMIT)],
    )
    repeat = models.CharField(
        max_length=10,
        choices=Repeat.choices,
        default=Repeat.NONE,
    )
    # The to-do that Done made from this one. Emptied when that one is deleted.
    # editable=False: never in a form or the admin.
    next_todo = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # The day of the month a monthly to-do comes back on. A form that sets or
    # changes the due date or the repeat sets it; copies keep it. None: use
    # the due date's own day.
    repeat_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        editable=False,
    )
    # True once a person saved this to-do on the edit page or in the admin.
    # Undo never deletes an edited copy.
    edited = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TodoQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.title

    @property
    def repeats(self):
        return self.repeat != self.Repeat.NONE

    def clean(self):
        super().clean()
        if self.repeats and self.due_date is None:
            # Tied to the field "repeat": every Todo ModelForm must include it.
            raise ValidationError({"repeat": "A repeating to-do needs a due date."})

    def next_values(self):
        """The fields of the next copy: what is copied, and the next due date.

        Raises OverflowError when the next date would be after 31 Dec 9999.
        """
        start = self.due_date or timezone.localdate()
        # Without a remembered day (an old row, the shell), the copy remembers
        # the day it was counted from, so it does not drift after that.
        day = self.repeat_day or start.day
        return {
            "title": self.title,
            "notes": self.notes,
            "priority": self.priority,
            "repeat": self.repeat,
            "repeat_day": day,
            "due_date": rp.next_due_date(start, self.repeat, day),
        }

    def next_copy(self):
        """The next to-do of a repeating one, not saved yet."""
        return Todo(**self.next_values())

    def copy_subtasks_to(self, copy):
        """Give the saved next copy the same steps, in order, all not done.

        One INSERT for all of them (bulk_create). Only the titles are copied.
        """
        Subtask.objects.bulk_create(
            [Subtask(todo=copy, title=title) for title in self.subtask_titles()]
        )

    def subtask_titles(self):
        """The titles of this to-do's steps, oldest first."""
        return list(self.subtasks.values_list("title", flat=True))

    def set_done(self, target):
        """Done (target=True) or Undo (target=False). Does nothing if it is already so.

        Done on a repeating to-do makes the next copy (none after the year
        9999). Undo deletes that copy only if it is open, has no next copy of
        its own, and nobody edited it.
        """
        with transaction.atomic():
            # Claim the change: only the request whose UPDATE changed the row
            # goes on. This guards real concurrency on a database that lets
            # two writers in at once (PostgreSQL). SQLite lets one writer in
            # at a time, so no SQLite test can show that race; the test with
            # two stale objects shows the "already done" case.
            claimed = Todo.objects.filter(pk=self.pk, done=not target).update(
                done=target
            )
            if not claimed:
                return
            fresh = Todo.objects.get(pk=self.pk)
            if target:
                if fresh.repeats and fresh.next_todo_id is None:
                    try:
                        copy = fresh.next_copy()
                    except OverflowError:
                        return  # no date after 31 Dec 9999: Done, with no copy
                    copy.save()
                    # Same transaction: the copy and its steps, or neither.
                    fresh.copy_subtasks_to(copy)
                    Todo.objects.filter(pk=fresh.pk).update(next_todo=copy)
            elif fresh.next_todo_id is not None:
                # The copy's own state decides, in one conditional DELETE.
                # Never build the copy again from the original: the original
                # may have changed since Done (even its repeat).
                # A change to the copy's steps sets its `edited` (the step views).
                Todo.objects.filter(
                    pk=fresh.next_todo_id,
                    done=False,
                    next_todo=None,
                    edited=False,
                ).delete()  # SET_NULL empties fresh.next_todo


class SubtaskQuerySet(models.QuerySet):
    """Queries for steps. Empty for now; later step queries go here."""


class Subtask(models.Model):
    """A step inside a to-do. On the page it is called a "step"."""

    # CASCADE: when a to-do is deleted, its steps are deleted too.
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="subtasks")
    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SubtaskQuerySet.as_manager()

    class Meta:
        # Oldest first. The id breaks a tie when two steps have the same time.
        ordering = ["created_at", "pk"]

    def __str__(self):
        return self.title
