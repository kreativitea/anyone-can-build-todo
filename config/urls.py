from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import include, path

from todos.views import signup

urlpatterns = [
    path("admin/", admin.site.urls),
    # Accounts. Not include("django.contrib.auth.urls"): that also adds the
    # password-reset pages, which need email.
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    # Open to visitors: an old tab whose session ended can still log out.
    path(
        "accounts/logout/",
        login_not_required(auth_views.LogoutView.as_view()),
        name="logout",
    ),
    path("accounts/signup/", signup, name="signup"),
    path("", include("todos.urls")),
]
