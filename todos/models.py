from django.db import models


class TodoQuerySet(models.QuerySet):
    def remaining(self):
        """The to-dos that are not done yet."""
        return self.filter(done=False)

    def completed(self):
        """The to-dos that are done."""
        return self.filter(done=True)


class Todo(models.Model):
    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TodoQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.title
