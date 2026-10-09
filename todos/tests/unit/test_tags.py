"""Tags (feature 14): the name cleaning, the Tags box, and who owns a tag.

Ana and ben each have their list "My to-dos". Tags belong to the LIST's owner.
"""

from django.db import IntegrityError, transaction
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase

from todos.forms import TodoEditForm, TodoForm
from todos.models import Tag, Todo, clean_tag_name
from todos.tests.integration.helpers import first_list, make_user
from todos.views import list_params

# Invisible characters, written as code points so no editor can lose them.
ZERO_WIDTH_SPACE = "​"
SOFT_HYPHEN = "­"


class CleanTagNameTests(SimpleTestCase):
    def test_clean_tag_name(self):
        rows = [
            (" Home ", "home"),  # spaces at the ends, small letters
            ("ｈｏｍｅ", "home"),  # wide letters (NFKC)
            ("go   shopping", "go shopping"),  # many spaces become one
            ("a　b", "a b"),  # the Japanese wide space
            ("a\x00b", "a b"),  # a control character becomes a space
            ("a\tb", "a b"),  # a tab too
            (f"home{ZERO_WIDTH_SPACE}", "home"),  # format characters are removed
            (f"{SOFT_HYPHEN}home", "home"),
            ("#home", "#home"),  # a # is kept
            ("# home", "# home"),
            ("##home", "##home"),
            ("CAFÉ", "café"),  # small letters, not only A to Z
            ("牛乳", "牛乳"),  # Japanese is unchanged
            ("", ""),  # nothing left
            ("   ", ""),
            (ZERO_WIDTH_SPACE, ""),
        ]
        for text, expected in rows:
            with self.subTest(text=text):
                self.assertEqual(clean_tag_name(text), expected)
                # Cleaning twice gives the same as cleaning once.
                self.assertEqual(clean_tag_name(clean_tag_name(text)), expected)


class TagFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = make_user("ana")
        cls.anas = first_list(cls.ana)

    def form(self, tag_names):
        return TodoForm({"title": "Buy milk", "tag_names": tag_names})

    def test_form_parses_tags(self):
        rows = [
            ("home, Urgent,,HOME, ", ["home", "urgent"]),
            ("牛乳、買い物", ["牛乳", "買い物"]),  # the Japanese comma
            ("a，b", ["a", "b"]),  # the wide comma (NFKC)
            ("a﹐b", ["a", "b"]),  # the small comma (NFKC)
            ("#home, ##home, # home", ["#home", "##home", "# home"]),
            (f"home, home{ZERO_WIDTH_SPACE}", ["home"]),  # invisible: the same tag
            ("", []),
        ]
        for text, expected in rows:
            with self.subTest(text=text):
                form = self.form(text)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["tag_names"], expected)

    def test_form_refuses_a_long_tag(self):
        form = self.form("a" * 31)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["tag_names"], ["A tag can be at most 30 characters."]
        )
        form = self.form("a" * 30)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_refuses_too_many_tags(self):
        form = self.form("a,b,c,d,e,f")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["tag_names"], ["At most 5 tags on one to-do."])
        for text in ["a,b,c,d,e", "a,a,a,a,a,a,b"]:
            with self.subTest(text=text):
                form = self.form(text)
                self.assertTrue(form.is_valid(), form.errors)

    def test_form_with_errors_keeps_the_input(self):
        form = self.form("a,b,c,d,e,f")
        self.assertFalse(form.is_valid())
        self.assertHTMLEqual(
            str(form["tag_names"]),
            '<input type="text" name="tag_names" value="a,b,c,d,e,f" '
            'placeholder="home, urgent" maxlength="200" aria-invalid="true" '
            'aria-describedby="id_tag_names_helptext id_tag_names_error" '
            'id="id_tag_names">',
        )

    def test_new_form_has_an_empty_tags_box(self):
        self.assertHTMLEqual(
            str(TodoForm()["tag_names"]),
            '<input type="text" name="tag_names" placeholder="home, urgent" '
            'maxlength="200" aria-describedby="id_tag_names_helptext" '
            'id="id_tag_names">',
        )
        self.assertEqual(TodoForm()["tag_names"].label, "Tags")
        self.assertEqual(TodoForm()["tag_names"].help_text, "separated by commas")

    def test_edit_form_shows_saved_tags(self):
        todo = Todo.objects.create(todo_list=self.anas, title="Buy milk")
        todo.set_tags(["urgent", "home"])
        form = TodoEditForm(instance=todo, user=self.ana)
        self.assertEqual(form["tag_names"].value(), "home, urgent")  # a-b-c order

    def test_save_with_commit_false_saves_tags_with_save_m2m(self):
        form = self.form("home, urgent")
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.todo_list = self.anas
        todo = form.save(commit=False)
        todo.save()
        self.assertEqual(list(todo.tags.values_list("name", flat=True)), [])
        form.save_m2m()
        self.assertEqual(
            list(todo.tags.values_list("name", flat=True)), ["home", "urgent"]
        )


class TagParamsTests(SimpleTestCase):
    def test_list_params_keeps_a_tag(self):
        rows = [
            ("tag=Home", {"tag": "home"}),
            ("tag=go%20shopping", {"tag": "go shopping"}),
            ("tag=%EF%BD%88%EF%BD%8F%EF%BD%8D%EF%BD%85", {"tag": "home"}),  # ｈｏｍｅ
            ("tag=", {}),
            ("tag=%20", {}),
            ("tag=" + "a" * 31, {}),
            ("tag=" + "a" * 30, {"tag": "a" * 30}),
        ]
        for query, expected in rows:
            with self.subTest(query=query):
                self.assertEqual(list_params(QueryDict(query)), expected)

    def test_tag_comes_after_sort_and_before_selected(self):
        query = "selected=5&tag=home&sort=title&q=milk&show=active"
        self.assertEqual(
            list(list_params(QueryDict(query))),
            ["show", "q", "sort", "tag", "selected"],
        )


class TagModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = make_user("ana")
        cls.ben = make_user("ben")
        cls.anas = first_list(cls.ana)
        cls.bens = first_list(cls.ben)

    def test_set_tags_uses_the_list_owner(self):
        todo = Todo.objects.create(todo_list=self.anas, title="Buy milk")
        todo.set_tags(["Home", "home", ""])
        self.assertEqual(
            list(todo.tags.values_list("name", "owner")), [("home", self.ana.pk)]
        )

    def test_set_tags_replaces_the_tags(self):
        todo = Todo.objects.create(todo_list=self.anas, title="Buy milk")
        todo.set_tags(["home", "urgent"])
        todo.set_tags(["work"])
        self.assertEqual(list(todo.tags.values_list("name", flat=True)), ["work"])

    def test_set_tags_on_bens_list_makes_bens_tag(self):
        # Whoever calls it: the tag is the LIST owner's.
        todo = Todo.objects.create(todo_list=self.bens, title="Ben's")
        todo.set_tags(["home"])
        self.assertEqual(todo.tags.get().owner, self.ben)

    def test_tag_names_are_unique_per_person(self):
        Tag.objects.create(owner=self.ana, name="home")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tag.objects.create(owner=self.ana, name="home")
        Tag.objects.create(owner=self.ben, name="home")
        self.assertEqual(Tag.objects.filter(name="home").count(), 2)

    def test_tags_come_in_name_order(self):
        todo = Todo.objects.create(todo_list=self.anas, title="Buy milk")
        todo.set_tags(["urgent", "home", "after"])
        self.assertEqual(
            [tag.name for tag in todo.tags.all()], ["after", "home", "urgent"]
        )

    def test_owned_by_gives_only_their_tags(self):
        mine = Tag.objects.create(owner=self.ana, name="home")
        Tag.objects.create(owner=self.ben, name="home")
        self.assertEqual(list(Tag.objects.owned_by(self.ana)), [mine])

    def test_str_is_the_name(self):
        self.assertEqual(str(Tag(owner=self.ana, name="home")), "home")
