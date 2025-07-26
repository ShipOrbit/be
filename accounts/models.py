from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator
import uuid


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=15)
    last_name = models.CharField(max_length=255)
    phone_number = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r"^\+?[1-9]\d{1,14}$",
                message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.",
            )
        ],
    )
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True, null=True)
    password_reset_token = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    stripe_customer_id = models.CharField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "users"
