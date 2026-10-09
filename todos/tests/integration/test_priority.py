from django.test import TestCase
from django.urls import reverse

from todos.models import Todo
from todos.tests.integration.helpers import PRIORITY_SELECT

# The labels on the list, as whole elements.
HIGH_LABEL = '<span class="priority high">High priority</span>'
MEDIUM_LABEL = '<span class="priority medium">Medium priority</span>'
LOW_LABEL = '<span class="priority low">Low priority</span>'

# The title box after a failed post, as the whole element: it keeps "Buy milk".
TITLE_BOX_WITH_BUY_MILK = (
    '<input type="text" name="title" value="Buy milk" aria-label="New to-do" '
    'placeholder="What needs doing?" autofocus maxlength="200" required '
    'id="id_title">'
)


class PriorityTests(TestCase):
    # New behaviour.

    def test_list_page_has_a_priority_box(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(
            response, '<label for="id_priority">Priority:</label>', count=1, html=True
        )
        self.assertContains(response, PRIORITY_SELECT, count=1, html=True)

    def test_add_a_high_priority_todo(self):
        response = self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "priority": "3"}
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(Todo.objects.get().priority, Todo.Priority.HIGH)

    def test_unknown_priority_shows_an_error_and_keeps_the_title(self):
        response = self.client.post(
            reverse("todo_add"), {"title": "Buy milk", "priority": "9"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Todo.objects.count(), 0)
        self.assertContains(
            response,
            "<li>Select a valid choice. 9 is not one of the available choices.</li>",
            count=1,
            html=True,
        )
        self.assertContains(response, TITLE_BOX_WITH_BUY_MILK, count=1, html=True)

    def test_high_label_is_shown_and_medium_has_none(self):
        Todo.objects.create(title="Call home", priority=Todo.Priority.HIGH)
        Todo.objects.create(title="Buy milk", priority=Todo.Priority.MEDIUM)
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, HIGH_LABEL, count=1, html=True)
        self.assertContains(response, MEDIUM_LABEL, count=0, html=True)
        self.assertContains(response, LOW_LABEL, count=0, html=True)

    def test_low_label_is_shown(self):
        Todo.objects.create(title="Read chapter 3", priority=Todo.Priority.LOW)
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, LOW_LABEL, count=1, html=True)

    # What already works, and must keep working.

    def test_title_only_post_still_goes_back_to_the_list(self):
        response = self.client.post(reverse("todo_add"), {"title": "Buy milk"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(Todo.objects.count(), 1)
