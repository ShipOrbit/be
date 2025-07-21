import uuid

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from shipper.models import Company

from .models import User


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    company_name = serializers.CharField(write_only=True)
    primary_ships_country = serializers.CharField(
        write_only=True,
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "password",
            "company_name",
            "primary_ships_country",
        ]

    def create(self, validated_data):
        company_name = validated_data.pop("company_name")
        primary_ships_country = validated_data.pop(
            "primary_ships_country",
        )

        # Create user
        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            phone_number=validated_data["phone_number"],
            password=validated_data["password"],
            email_verification_token=str(uuid.uuid4()),
        )

        # Create company
        Company.objects.create(
            user=user, name=company_name, primary_ships_country=primary_ships_country
        )

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(style={"input_type": "password"})

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")

        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError("Invalid email or password.")
            if not user.is_active:
                raise serializers.ValidationError("User account is disabled.")
            data["user"] = user
        else:
            raise serializers.ValidationError("Must include email and password.")

        return data


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(validators=[validate_password])

    def validate_token(self, value):
        try:
            user = User.objects.get(password_reset_token=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid token.")
        return value


class UserSerializer(serializers.ModelSerializer):
    company = serializers.SerializerMethodField()
    shipping_needs = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "is_email_verified",
            "company",
            "shipping_needs",
        ]

    def get_company(self, obj):
        if hasattr(obj, "company"):
            return {
                "name": obj.company.name,
                "location": obj.company.location,
                "primary_ships_country": obj.company.primary_ships_country,
            }
        return None

    def get_shipping_needs(self, obj):
        if hasattr(obj, "shipping_needs"):
            return {
                "mode": obj.shipping_needs.mode,
                "average_ftl": obj.shipping_needs.average_ftl,
                "trailer_type": obj.shipping_needs.trailer_type,
            }
        return None


class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, value):
        try:
            user = User.objects.get(email_verification_token=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid verification token or email is already verified."
            )
        return value
