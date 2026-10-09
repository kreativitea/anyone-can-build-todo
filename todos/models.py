from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models, transaction
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

        Used to MAKE the copy and to check that a copy is untouched, so the
        two can never disagree.
        """
        start = self.due_date or timezone.localdate()
        return {
            "title": self.title,
            "notes": self.notes,
            "priority": self.priority,
            "repeat": self.repeat,
            "due_date": rp.next_due_date(start, self.repeat),
        }

    def next_copy(self):
        """The next to-do of a repeating one, not saved yet."""
        return Todo(**self.next_values())

    def is_untouched_copy_of(self, original):
        """True if this to-do is still exactly what Done made from `original`."""
        return all(
            getattr(self, name) == value
            for name, value in original.next_values().items()
        )

    def set_done(self, target):
        """Done (target=True) or Undo (target=False). Does nothing if it is already so.

        Done on a repeating to-do makes the next copy. Undo deletes that copy
        only if it is open, has no next copy of its own, and was not changed.
        Safe when two requests come at once: the UPDATE claims the change, and
        only the request that changed the row goes on.
        """
        with transaction.atomic():
            claimed = Todo.objects.filter(pk=self.pk, done=not target).update(
                done=target
            )
            if not claimed:
                return
            fresh = Todo.objects.get(pk=self.pk)
            if target:
                if fresh.repeats and fresh.next_todo_id is None:
                    copy = fresh.next_copy()
                    copy.save()
                    Todo.objects.filter(pk=fresh.pk).update(next_todo=copy)
            elif fresh.next_todo_id is not None:
                copy = fresh.next_todo
                if (
                    not copy.done
                    and copy.next_todo_id is None
                    and copy.is_untouched_copy_of(fresh)
                    # Feature 15 adds: and copy.has_untouched_subtasks_of(fresh)
                ):
                    copy.delete()  # SET_NULL empties fresh.next_todo
