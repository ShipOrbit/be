import uuid

import resend
from django.conf import settings
from django.contrib.auth import login
from django.template.loader import render_to_string
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import User
from .serializers import (
    EmailVerificationSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    # ShippingNeedsSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)

resend.api_key = settings.RESEND_API_KEY


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def register_step_one(request):
    """
    Handle user registration (step 1)
    """
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        login(request, user)

        # Create or get token
        token, created = Token.objects.get_or_create(user=user)

        user_serializer = UserSerializer(user)

        try:
            send_verification_email(user)
        except Exception:
            pass

        return Response(
            {
                "message": "User registered successfully",
                "token": token.key,
                "user": user_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """
    Handle user login
    """
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data["user"]
        login(request, user)

        # Create or get token
        token, created = Token.objects.get_or_create(user=user)

        user_serializer = UserSerializer(user)

        return Response(
            {
                "token": token.key,
                "user": user_serializer.data,
                "message": "Login successful",
            },
            status=status.HTTP_200_OK,
        )

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def password_reset_request(request):
    """
    Handle password reset request
    """
    serializer = PasswordResetSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data["email"]
        user = User.objects.get(email=email)

        # Generate reset token
        reset_token = str(uuid.uuid4())
        user.password_reset_token = reset_token
        user.save()

        # TODO: Send password reset email
        # send_password_reset_email(user, reset_token)

        return Response(
            {"message": "Password reset email sent successfully"},
            status=status.HTTP_200_OK,
        )

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def password_reset_confirm(request):
    """
    Handle password reset confirmation
    """
    serializer = PasswordResetConfirmSerializer(data=request.data)
    if serializer.is_valid():
        token = serializer.validated_data["token"]
        password = serializer.validated_data["password"]

        user = User.objects.get(password_reset_token=token)
        user.set_password(password)
        user.password_reset_token = None
        user.save()

        return Response(
            {"message": "Password reset successfully"}, status=status.HTTP_200_OK
        )

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def verify_email(request):
    """
    Handle email verification
    """
    serializer = EmailVerificationSerializer(data=request.data)
    if serializer.is_valid():
        token = serializer.validated_data["token"]
        user = User.objects.get(email_verification_token=token)

        if user.is_email_verified:
            return Response(
                {"message": "Email already verified"}, status=status.HTTP_200_OK
            )

        user.is_email_verified = True
        user.email_verification_token = None
        user.save()

        return Response(
            {"message": "Email verified successfully"}, status=status.HTTP_200_OK
        )
    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def resend_verification_email(request):
    """
    Resend email verification
    """
    email = request.user

    if not email:
        return Response(
            {"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email)
        if user.is_email_verified:
            return Response(
                {"message": "Email already verified"}, status=status.HTTP_200_OK
            )

        # Generate new verification token
        user.email_verification_token = str(uuid.uuid4())
        user.save()
        try:
            send_verification_email(user)
        except Exception:
            return Response(
                {"message": "Please Try again later"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"message": "Verification email sent successfully"},
            status=status.HTTP_200_OK,
        )

    except User.DoesNotExist:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def user_profile(request):
    """
    Get user profile
    """
    serializer = UserSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)


# Helper functions (to be implemented)
def send_verification_email(user):
    """
    Send email verification email
    """
    subject = "Verify your ShipOrbit account"
    # message = f'Click the link to verify your account: {settings.FRONTEND_URL}/verify-email/{user.email_verification_token}'
    html_message = render_to_string(
        "verification_email.html",
        {
            "first_name": user.first_name,
            "verify_link": f"{settings.FRONTEND_URL}/verify-email/{user.email_verification_token}",
        },
    )
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user.email]
    resend.Emails.send(
        {
            "from": from_email,
            "to": recipient_list,
            "subject": subject,
            "html": html_message,
        }
    )
    pass


def send_password_reset_email(user, token):
    """
    Send password reset email
    """
    subject = "Reset your ShipOrbit password"
    message = f"Click the link to reset your password: {settings.FRONTEND_URL}/reset-password/{token}"
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user.email]

    # send_mail(subject, message, from_email, recipient_list)
    pass
