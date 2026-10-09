"""Our middleware: code that runs for every request, before the view."""

from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import resolve_url
from django.urls import reverse


class LoginRequired(LoginRequiredMiddleware):
    """Django's: every page needs log-in. But a POST (anything but GET or HEAD) sends the
    person back to the list after log-in.

    After log-in the browser GETs the `next` address. A POST-only address
    would then answer 405, so for anything but GET, `next` is the list. The
    POST itself is not done: the person sees the list and presses again.
    """

    def handle_no_permission(self, request, view_func):
        if request.method in ("GET", "HEAD"):
            return super().handle_no_permission(request, view_func)
        return redirect_to_login(
            reverse("todo_list"),
            resolve_url(self.get_login_url(view_func)),
            self.get_redirect_field_name(view_func),
        )
