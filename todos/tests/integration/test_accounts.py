"""Accounts (17): sign up, log in, log out, and what a visitor may see.

The addresses are written out ("/accounts/login/"), not reversed, so a test
fails with a clear message when an address is missing.
"""

import os
import subprocess
import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from todos.models import Subtask, Todo, TodoList
from todos.tests.integration.helpers import (
    LOGIN_URL,
    LOGOUT_URL,
    SIGNUP_URL,
    TEST_PASSWORD,
    LoggedInTestCase,
    account_bar,
    count_elements,
    first_list,
    list_path,
    make_user,
    page_forms,
    page_without_csrf,
)

User = get_user_model()

NEXT_LIST = f"{LOGIN_URL}?next=/"


def tables():
    """Every row of the three tables, to check that nothing changed."""
    return (
        list(TodoList.objects.values()),
        list(Todo.objects.values()),
        list(Subtask.objects.values()),
    )


class VisitorTests(TestCase):
    """A visitor (not logged in) sees only the log-in and sign-up pages."""

    @classmethod
    def setUpTestData(cls):
        cls.ana = make_user("ana")
        cls.todo_list = first_list(cls.ana)
        cls.milk = Todo.objects.create(todo_list=cls.todo_list, title="Buy milk")
        cls.flour = Subtask.objects.create(todo=cls.milk, title="Buy flour")

    def test_visitor_is_sent_to_log_in(self):
        response = self.client.get("/")
        self.assertRedirects(response, NEXT_LIST, fetch_redirect_response=False)

    def test_visitor_get_of_any_page_comes_back_to_it_after_log_in(self):
        pk = self.milk.pk
        list_id = self.todo_list.pk
        for url in [
            f"/{pk}/edit/",
            f"/{pk}/subtasks/",
            "/?show=active",
            f"/lists/{list_id}/?show=active",
            "/lists/new/",
            f"/lists/{list_id}/edit/",
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    f"{LOGIN_URL}?next={url.replace('?', '%3F').replace('=', '%3D')}",
                    fetch_redirect_response=False,
                )

    def test_visitor_head_is_like_get(self):
        # HEAD is a GET without the body: after log-in the page itself is fine.
        pk = self.milk.pk
        for url in [f"/{pk}/edit/", "/"]:
            with self.subTest(url=url):
                response = self.client.head(url)
                self.assertRedirects(
                    response, f"{LOGIN_URL}?next={url}", fetch_redirect_response=False
                )

    def test_visitor_post_changes_nothing_and_comes_back_to_the_list(self):
        # After log-in the browser would GET the address; a POST-only
        # address would answer 405. So every POST goes back to the list.
        pk, step = self.milk.pk, self.flour.pk
        list_id = self.todo_list.pk
        posts = [
            (f"/lists/{list_id}/add/", {"title": "Hacked"}),
            (f"/{pk}/toggle/", {"done": "1"}),
            (f"/{pk}/edit/", {"title": "Hacked"}),
            (f"/{pk}/delete/", {}),
            (f"/lists/{list_id}/delete-completed/", {"ids": [str(pk)]}),
            (f"/{pk}/subtasks/add/", {"title": "Hacked"}),
            (f"/{pk}/subtasks/{step}/done/", {"done": "1"}),
            (f"/{pk}/subtasks/{step}/delete/", {}),
            ("/lists/new/", {"name": "Hacked"}),
            (f"/lists/{list_id}/edit/", {"name": "Hacked"}),
            (f"/lists/{list_id}/delete/", {}),
        ]
        before = tables()
        for url, data in posts:
            with self.subTest(url=url):
                response = self.client.post(url, data)
                self.assertRedirects(response, NEXT_LIST, fetch_redirect_response=False)
                self.assertEqual(tables(), before)

    def test_login_and_signup_pages_are_open(self):
        for url, heading in [(LOGIN_URL, "Log in"), (SIGNUP_URL, "Sign up")]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f"<h1>{heading}</h1>", html=True)
                self.assertEqual(count_elements(response, "h1", None), 1)

    def test_log_in_page_has_no_account_bar(self):
        response = self.client.get(LOGIN_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(count_elements(response, "div", "account"), 0)

    def test_log_in_page_links_to_sign_up_and_back(self):
        login = self.client.get(LOGIN_URL)
        self.assertContains(login, f'<a href="{SIGNUP_URL}">Sign up</a>', html=True)
        signup = self.client.get(SIGNUP_URL)
        self.assertContains(signup, f'<a href="{LOGIN_URL}">Log in</a>', html=True)

    def test_log_in_form_has_its_labels(self):
        response = self.client.get(LOGIN_URL)
        self.assertContains(
            response, '<label for="id_username">Username:</label>', html=True
        )
        self.assertContains(
            response, '<label for="id_password">Password:</label>', html=True
        )

    def test_admin_log_in_stays_open(self):
        # What Django 5.2 does, pinned: the admin's front page and its own
        # log-in page are open to visitors (the admin checks staff itself);
        # its other pages need log-in, so a visitor goes to OUR log-in page.
        # A staff person logs in there and is sent on to the admin.
        self.assertRedirects(
            self.client.get("/admin/"),
            "/admin/login/?next=%2Fadmin%2F",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get("/admin/todos/todo/"),
            f"{LOGIN_URL}?next=%2Fadmin%2Ftodos%2Ftodo%2F",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)

    def test_admin_is_closed_to_a_person_who_is_not_staff(self):
        self.client.force_login(self.ana)
        response = self.client.get("/admin/todos/todo/")
        self.assertRedirects(
            response,
            "/admin/login/?next=%2Fadmin%2Ftodos%2Ftodo%2F",
            fetch_redirect_response=False,
        )


class SignUpTests(TestCase):
    def sign_up(self, username="ben", password1=TEST_PASSWORD, password2=None):
        return self.client.post(
            SIGNUP_URL,
            {
                "username": username,
                "password1": password1,
                "password2": password1 if password2 is None else password2,
            },
        )

    def test_signup_makes_a_user_and_logs_in(self):
        response = self.sign_up("ben")
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        ben = User.objects.get(username="ben")
        self.assertTrue(ben.check_password(TEST_PASSWORD))
        self.assertEqual(
            self.client.get(list_path(first_list(ben).pk)).status_code, 200
        )
        self.assertEqual(self.client.session["_auth_user_id"], str(ben.pk))

    def test_signup_rejects_a_common_password(self):
        response = self.sign_up("ben", "password123")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "<li>This password is too common.</li>", count=1, html=True
        )
        self.assertFalse(User.objects.exists())

    def test_signup_rejects_different_passwords(self):
        response = self.sign_up("ben", TEST_PASSWORD, "another-plum-tree-43")
        self.assertEqual(response.status_code, 200)
        # Django's own words, with a curly apostrophe.
        self.assertContains(
            response,
            "<li>The two password fields didn’t match.</li>",
            count=1,
            html=True,
        )
        self.assertFalse(User.objects.exists())

    def test_signup_rejects_a_taken_username(self):
        make_user("ben")
        response = self.sign_up("ben")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<li>A user with that username already exists.</li>",
            count=1,
            html=True,
        )
        self.assertEqual(User.objects.count(), 1)

    def test_logged_in_person_on_sign_up_goes_to_the_list(self):
        self.client.force_login(make_user("ana"))
        response = self.client.get(SIGNUP_URL)
        self.assertRedirects(response, "/", fetch_redirect_response=False)


class LogInTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = make_user("ana")

    def log_in(self, password=TEST_PASSWORD, url=LOGIN_URL):
        return self.client.post(url, {"username": "ana", "password": password})

    def test_login_with_a_good_password(self):
        response = self.log_in()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.ana.pk))

    def test_login_with_a_bad_password(self):
        response = self.log_in("wrong-password-99")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<li>Please enter a correct username and password. Note that both "
            "fields may be case-sensitive.</li>",
            count=1,
            html=True,
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_goes_on_to_the_page_asked_for(self):
        response = self.log_in(url=f"{LOGIN_URL}?next=/%3Fshow%3Dactive")
        self.assertRedirects(response, "/?show=active", fetch_redirect_response=False)

    def test_login_never_goes_to_another_site(self):
        response = self.log_in(url=f"{LOGIN_URL}?next=https://evil.example/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_logged_in_person_on_log_in_goes_to_the_list(self):
        self.client.force_login(self.ana)
        response = self.client.get(LOGIN_URL)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_logout_is_post_only(self):
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(LOGOUT_URL).status_code, 405)
        response = self.client.post(LOGOUT_URL)
        self.assertRedirects(response, LOGIN_URL, fetch_redirect_response=False)
        response = self.client.get("/")
        self.assertRedirects(response, NEXT_LIST, fetch_redirect_response=False)

    def test_logout_when_already_logged_out(self):
        # An old tab: the session ended, then the person presses Log out.
        response = self.client.post(LOGOUT_URL)
        self.assertRedirects(response, LOGIN_URL, fetch_redirect_response=False)


class AccountBarTests(LoggedInTestCase):
    def test_account_bar_shows_who_is_logged_in(self):
        for url in [self.list_url(), f"/{self.make_todo(title='Buy milk').pk}/edit/"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertInHTML(
                    account_bar("ana"), page_without_csrf(response), count=1
                )

    def test_log_out_button_works_with_csrf_checks_on(self):
        # Like a real browser: the Log out form sends its own CSRF token.
        client = self.csrf_client()
        page = client.get(self.list_url())
        forms = [f for f in page_forms(page) if f.action == LOGOUT_URL]
        self.assertEqual(len(forms), 1, "want one Log out form")
        [form] = forms
        self.assertEqual(form.method, "post")
        self.assertIn("csrfmiddlewaretoken", form.fields)
        response = client.post(form.action, form.data(form.buttons[0]))
        self.assertRedirects(response, LOGIN_URL, fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", client.session)


class SecretKeyTests(SimpleTestCase):
    def start(self, code="import django; django.setup()", **env):
        """Run `code` in a new Python that loads the settings, with these
        environment variables (and no DJANGO_SECRET_KEY or DJANGO_DEBUG of ours).
        """
        clean = {
            k: v
            for k, v in os.environ.items()
            if k not in {"DJANGO_SECRET_KEY", "DJANGO_DEBUG"}
        }
        return subprocess.run(
            [sys.executable, "-c", code],
            env={**clean, "DJANGO_SETTINGS_MODULE": "config.settings", **env},
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
        )

    def test_no_secret_key_on_a_live_server_refuses_to_start(self):
        result = self.start(DJANGO_DEBUG="False")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "ImproperlyConfigured: Set DJANGO_SECRET_KEY on a live server.",
            result.stderr,
        )

    def test_an_empty_blank_or_laptop_key_on_a_live_server_refuses_to_start(self):
        for key in [
            "",
            "   ",
            "django-insecure-only-for-your-laptop",
            "django-insecure-x",
        ]:
            with self.subTest(key=key):
                result = self.start(DJANGO_DEBUG="False", DJANGO_SECRET_KEY=key)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "ImproperlyConfigured: Set DJANGO_SECRET_KEY on a live server.",
                    result.stderr,
                )

    def test_a_live_server_keeps_its_cookies_safe(self):
        code = (
            "import django; django.setup(); from django.conf import settings as s; "
            "print(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, "
            "s.SESSION_COOKIE_HTTPONLY)"
        )
        # A test value only, not a real key.
        result = self.start(
            code, DJANGO_DEBUG="False", DJANGO_SECRET_KEY="test-only-key"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["True", "True", "True"])

    def test_a_live_server_with_a_secret_key_starts(self):
        # A test value only, not a real key.
        result = self.start(DJANGO_DEBUG="False", DJANGO_SECRET_KEY="test-only-key")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_laptop_starts_without_a_secret_key(self):
        result = self.start()
        self.assertEqual(result.returncode, 0, result.stderr)
