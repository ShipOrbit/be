from django.urls import path
from . import views

# App URLs (accounts/urls.py)
app_name = "accounts"

urlpatterns = [
    # Authentication
    path("auth/register/", views.register, name="register"),
    # path('auth/register/step-2/', views.register_step_two, name='register_step_two'),
    path("auth/login/", views.login_view, name="login"),
    # path('auth/logout/', views.logout_view, name='logout'),
    # Password Reset
    path(
        "auth/password-reset/request/",
        views.password_reset_request,
        name="password_reset_request",
    ),
    path(
        "auth/password-reset/confirm/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    # Email Verification
    path("auth/verify-email/", views.verify_email, name="verify_email"),
    path(
        "auth/resend-verification/",
        views.resend_verification_email,
        name="resend_verification",
    ),
    # User Profile
    path("auth/user/", views.user_profile, name="user_profile"),
]
