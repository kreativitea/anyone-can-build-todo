"""Tests for the test helper that reads forms, so it sends what a browser sends.

Every journey trusts `page_forms`. If it sent something a browser would not,
a journey could pass while the real page is broken. These tests use small
HTML strings, with no request and no database.
"""

from django.test import SimpleTestCase

from todos.tests.integration.helpers import PageForms, PageParts


def one_form(html, page_path="/"):
    forms = PageForms(html, page_path=page_path).forms
    assert len(forms) == 1, forms
    return forms[0]


class RepeatedNameTests(SimpleTestCase):
    def test_every_value_of_a_repeated_name_is_kept(self):
        # Like the delete-completed form: one hidden "ids" input per to-do.
        form = one_form(
            '<form class="delete-completed" method="post" action="/delete-completed/">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="t">'
            '<input type="hidden" name="ids" value="3">'
            '<input type="hidden" name="ids" value="5">'
            '<button type="submit">Delete 2 completed to-dos</button>'
            "</form>"
        )
        self.assertEqual(form.fields["ids"], ["3", "5"])
        self.assertEqual(
            form.data(form.buttons[0]),
            {"csrfmiddlewaretoken": ["t"], "ids": ["3", "5"]},
        )


class TextareaAndSelectTests(SimpleTestCase):
    def test_textarea_sends_its_text(self):
        # A browser drops one newline right after <textarea>.
        form = one_form(
            '<form method="post" action="/x/">'
            '<textarea name="notes">\nTwo lines\nof notes</textarea></form>'
        )
        self.assertEqual(form.fields, {"notes": ["Two lines\nof notes"]})

    def test_select_sends_the_selected_option(self):
        form = one_form(
            '<form method="post" action="/x/"><select name="priority">'
            '<option value="low">Low</option>'
            '<option value="medium" selected>Medium</option>'
            "</select></form>"
        )
        self.assertEqual(form.fields, {"priority": ["medium"]})

    def test_select_with_nothing_selected_sends_the_first_option(self):
        form = one_form(
            '<form method="post" action="/x/"><select name="priority">'
            '<option value="low">Low</option>'
            '<option value="medium">Medium</option>'
            "</select></form>"
        )
        self.assertEqual(form.fields, {"priority": ["low"]})

    def test_option_without_a_value_sends_its_text(self):
        form = one_form(
            '<form method="post" action="/x/"><select name="size">'
            "<option> Big </option></select></form>"
        )
        self.assertEqual(form.fields, {"size": ["Big"]})


class BrowserRuleTests(SimpleTestCase):
    def test_only_checked_boxes_and_the_checked_radio_are_sent(self):
        form = one_form(
            '<form method="post" action="/x/">'
            '<input type="checkbox" name="urgent">'
            '<input type="checkbox" name="pinned" checked>'
            '<input type="radio" name="colour" value="red">'
            '<input type="radio" name="colour" value="blue" checked>'
            "</form>"
        )
        self.assertEqual(form.fields, {"pinned": ["on"], "colour": ["blue"]})

    def test_disabled_fields_are_not_sent(self):
        form = one_form(
            '<form method="post" action="/x/">'
            '<input name="a" value="1" disabled>'
            '<textarea name="b" disabled>no</textarea>'
            '<select name="c" disabled><option>no</option></select>'
            '<input name="d" value="4">'
            "</form>"
        )
        self.assertEqual(form.fields, {"d": ["4"]})

    def test_input_type_submit_is_a_button(self):
        form = one_form(
            '<form method="post" action="/x/">'
            '<input type="submit" name="go" value="Save"></form>'
        )
        self.assertEqual(form.fields, {})
        self.assertEqual([b.text for b in form.buttons], ["Save"])
        self.assertEqual(form.data(form.buttons[0]), {"go": ["Save"]})

    def test_the_pressed_button_sends_its_own_name_and_value(self):
        form = one_form(
            '<form method="post" action="/1/toggle/">'
            '<button name="done" value="1">Done</button>'
            '<button name="done" value="0">Undo</button>'
            "</form>"
        )
        undo = form.buttons[1]
        self.assertEqual(form.data(undo), {"done": ["0"]})

    def test_buttons_that_do_not_submit_are_not_buttons(self):
        form = one_form(
            '<form method="post" action="/x/">'
            '<button type="button">Help</button><button type="reset">Clear</button>'
            '<input type="reset" value="Clear"><button disabled>Off</button>'
            "<button>Add</button></form>"
        )
        self.assertEqual([b.text for b in form.buttons], ["Add"])

    def test_typing_into_a_missing_field_fails(self):
        form = one_form('<form method="post" action="/x/"><input name="a"></form>')
        with self.assertRaisesMessage(AssertionError, "no field ['b']"):
            form.data(b="1")


class ButtonTextTests(SimpleTestCase):
    def test_text_pieces_are_joined_and_spaces_collapsed(self):
        form = one_form(
            '<form method="post" action="/x/"><button>\n  Delete\n'
            "  <span>2</span>completed  </button></form>"
        )
        self.assertEqual([b.text for b in form.buttons], ["Delete 2 completed"])

    def test_a_form_keeps_every_button(self):
        form = one_form(
            '<form method="post" action="/x/">'
            "<button>Save</button><button>Save and add another</button></form>"
        )
        self.assertEqual(
            [b.text for b in form.buttons], ["Save", "Save and add another"]
        )


class ActionTests(SimpleTestCase):
    def test_a_form_with_no_action_posts_to_the_page_itself(self):
        form = one_form('<form method="post"></form>', page_path="/?show=active")
        self.assertEqual(form.action, "/?show=active")

    def test_an_empty_action_posts_to_the_page_itself(self):
        form = one_form('<form method="post" action=""></form>', page_path="/2/edit/")
        self.assertEqual(form.action, "/2/edit/")

    def test_post_actions_come_from_the_same_reader(self):
        parts = PageParts(
            '<form method="get" action="/search/"></form>'
            '<form method="post" action="/add/"></form>'
            '<form method="POST"></form>',
            page_path="/?show=active",
        )
        self.assertEqual(parts.post_actions, ["/add/", "/?show=active"])
