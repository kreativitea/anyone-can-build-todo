import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models, transaction
from django.db.models import Count, Q
from django.utils import timezone

from . import repeat as rp

# The longest notes a to-do may have. The form gets it from max_length.
NOTES_LIMIT = 500

# The name of the list a new person gets when they sign up.
DEFAULT_LIST_NAME = "My to-dos"

# Tags (14): the longest tag name, and the most tags on one to-do.
TAG_MAX_LENGTH = 30
TAGS_PER_TODO = 5


def clean_tag_name(text):
    """A tag name: normal letters, no invisible characters, one space between words, small letters.

    NFKC turns wide letters into normal ones. A control character (a line
    break, a tab, "\\0") becomes a space; a format character (a zero-width
    space, a soft hyphen) is removed. "" means: not a tag. Cleaning twice
    gives the same as cleaning once.
    """
    text = unicodedata.normalize("NFKC", text)
    text = "".join(
        " " if unicodedata.category(ch) == "Cc" else ch
        for ch in text
        if unicodedata.category(ch) != "Cf"
    )
    return " ".join(text.split()).lower()


def list_name_key(name):
    """The form of a list name that two names must not share: NFKC, then casefold.

    NFKC turns wide letters into normal ones ("ＷＯＲＫ" is "WORK"), like search;
    casefold ignores big and small letters, also outside A to Z ("Ä" and "ä",
    "Straße" and "STRASSE").
    """
    return unicodedata.normalize("NFKC", name).casefold()


# Control characters (Cc: line breaks, tab, bell, ...) and the line and
# paragraph separators. Format characters (Cf) stay: emoji need the joiner.
REFUSED_IN_LIST_NAMES = {"Cc", "Zl", "Zp"}


def validate_list_name(name):
    """A list name is one line of text: no line breaks or other control characters.

    A migration imports this: never change what it accepts, write a new one.
    """
    if any(unicodedata.category(ch) in REFUSED_IN_LIST_NAMES for ch in name):
        raise ValidationError(
            "A list name cannot have line breaks or other control characters."
        )


class TodoListQuerySet(models.QuerySet):
    def for_user(self, user):
        """The lists this person may see and use. Today: the lists they own.

        Sharing (20) deletes this and puts visible_to / editable_by in its
        place, so every caller is checked again.
        """
        return self.filter(owner=user)

    def owned_by(self, user):
        """The lists this person owns. For rename, delete, the name check and `/`."""
        return self.filter(owner=user)

    def create_default(self, user):
        """The list a new person gets: "My to-dos"."""
        return self.create(owner=user, name=DEFAULT_LIST_NAME)


class TodoList(models.Model):
    """A list of to-dos, like "Work" or "Shopping". Every to-do is in one list."""

    # CASCADE: deleting a user deletes their lists (and so their to-dos).
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="todo_lists",
    )
    name = models.CharField(max_length=50, validators=[validate_list_name])
    # list_name_key(name), set by save(). Two lists of one person never share
    # it (the constraint below). NFKC can make a name longer, so no max length.
    name_key = models.TextField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TodoListQuerySet.as_manager()

    class Meta:
        # The order they were made in. The id breaks a tie.
        ordering = ["created_at", "pk"]
        constraints = [
            # One person cannot have "Work", "work" and "ＷＯＲＫ"; two people
            # can each have "Work". The form checks the same key first, with
            # a friendlier message; this is the safety net.
            models.UniqueConstraint(
                fields=["owner", "name_key"],
                name="todolist_unique_name_per_owner",
                violation_error_message="You already have a list with this name.",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name_key = list_name_key(self.name)
        super().save(*args, **kwargs)

    def validate_constraints(self, exclude=None):
        """Check the unique name also where a form leaves name_key out (it is
        never a field), like the admin.
        """
        self.name_key = list_name_key(self.name)
        if exclude:
            exclude = set(exclude) - {"name_key"}
        super().validate_constraints(exclude)


class TagQuerySet(models.QuerySet):
    def owned_by(self, user):
        """This person's own tags. Every tag query starts here."""
        return self.filter(owner=user)


class Tag(models.Model):
    """A short word on to-dos, like "home". It belongs to the owner of the
    to-do's list, and is used in all of that person's lists.

    The name is always cleaned (clean_tag_name) before it is saved, so the
    database only checks "the same text".
    """

    # CASCADE: deleting a user deletes their tags.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tags",
    )
    name = models.CharField(max_length=TAG_MAX_LENGTH)

    objects = TagQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            # One person has one "home"; two people can each have "home".
            models.UniqueConstraint(
                fields=["owner", "name"], name="unique_tag_name_per_owner"
            ),
        ]

    def __str__(self):
        return self.name


class TodoQuerySet(models.QuerySet):
    def for_user(self, user):
        """Only the to-dos this person may see: those in their lists. Every
        to-do query in a view starts here.

        The LIST decides, not Todo.owner, so sharing (20) only changes
        TodoList. It is one query: the lists are a subquery.
        """
        return self.filter(todo_list__in=TodoList.objects.for_user(user))

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

    # The owner of the to-do's list, always: save() sets it from the list.
    # Never in a form. CASCADE: deleting a user deletes their to-dos.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="todos",
    )
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
    # The list this to-do is in. Required. CASCADE: deleting a list deletes
    # its to-dos (owner decision).
    todo_list = models.ForeignKey(
        TodoList,
        on_delete=models.CASCADE,
        related_name="todos",
        verbose_name="list",
    )
    # Set only through TodoForm / TodoEditForm, which call set_tags.
    tags = models.ManyToManyField(Tag, blank=True, related_name="todos")

    objects = TodoQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # The owner always follows the list (CONVENTIONS, OWNERSHIP), so no
        # view has to remember it, and the two can never be different.
        self.owner_id = self.todo_list.owner_id
        super().save(*args, **kwargs)

    def set_tags(self, names):
        """Put exactly these tags on this to-do. Missing tags are made for the LIST's owner.

        The owner never comes from the form, the address or the person who is
        logged in: tags follow the list. The names are cleaned here, so every
        way in gives clean names; empty ones and repeats are dropped.
        """
        owner = self.todo_list.owner
        names = dict.fromkeys(n for n in map(clean_tag_name, names) if n)
        tags = [
            Tag.objects.owned_by(owner).get_or_create(owner=owner, name=name)[0]
            for name in names
        ]
        self.tags.set(tags)

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
            "owner_id": self.owner_id,
            "todo_list_id": self.todo_list_id,
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

    def mark_edited(self):
        """A change to the steps is an edit of the to-do (owner decision).

        So Undo on a repeating to-do never deletes a copy whose steps changed.
        One UPDATE; it never touches the to-do's `done`. The view found this
        to-do through its owner first.
        """
        # owner_id too: defence in depth, never a row of another person.
        Todo.objects.filter(pk=self.pk, owner_id=self.owner_id).update(edited=True)

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
                    # Same transaction: the copy, its steps and tags, or none.
                    fresh.copy_subtasks_to(copy)
                    # The same list, so the same owner's tags (tags, 14).
                    copy.tags.set(fresh.tags.all())
                    Todo.objects.filter(pk=fresh.pk).update(next_todo=copy)
            elif fresh.next_todo_id is not None:
                # The copy's own state decides, in one conditional DELETE.
                # Never build the copy again from the original: the original
                # may have changed since Done (even its repeat).
                # A change to the copy's steps sets its `edited` (the step views).
                # owner_id too: defence in depth, never a copy of another person.
                Todo.objects.filter(
                    pk=fresh.next_todo_id,
                    owner_id=fresh.owner_id,
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
