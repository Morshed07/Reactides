from rest_framework import serializers
from django.contrib.auth import authenticate
from django.forms import ValidationError
from .models import (
    User,
    EmailOTP,
    ShippingAddress
)
from .utils import (
    send_registration_otp_email,
    send_forgot_password_otp_email,
    get_tokens_for_user
)
from apps.representative.models import Representative


class RepresentativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Representative
        fields = (
            "id",
            "name",
            "email",
            "phone_number",
            "avatar",
            "company",
            "designation",
            "representative_code",
            "is_active"
        )
        read_only_fields = ("id",)


class UserSerializer(serializers.ModelSerializer):
    representative = serializers.SerializerMethodField()
    shipping_address = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "avatar",
            "mobile_number",
            "representative",
            "representative_code",
            "department",
            "job_title",
            "is_verified",
            "is_active",
            "shipping_address",
            "created_at"
        )
        read_only_fields = ("id", "is_verified", "created_at")

    def get_shipping_address(self, obj):
        shipping_address = ShippingAddress.objects.filter(user=obj).first()
        if shipping_address:
            return ShippingAddressSerializer(shipping_address).data
        return None
    

    def get_representative(self, obj):
        if obj.representative_code:
            representative = Representative.objects.filter(
                representative_code=obj.representative_code
            ).first()
            if representative:
                return RepresentativeSerializer(
                    representative,
                    context=self.context
                ).data
        return None


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "password",
            "confirm_password",
            "representative_code",
        )
        extra_kwargs = {
            "email": {"validators": []},
        }

    def validate_email(self, value):
        user = User.objects.filter(email=value).first()
        if user:
            if user.is_verified:
                raise serializers.ValidationError(
                    "User with this email already exists.",
                    code="already_exists"
                )
            else:
                raise serializers.ValidationError(
                    "Account not verified.",
                    code="pending_verification"
                )
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"password": "Passwords do not match"})
        return attrs

    def validate_representative_code(self, value):
        if not Representative.objects.filter(representative_code=value, is_active=True).exists():
            raise serializers.ValidationError("Invalid representative code.")
        return value

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name'),
            last_name=validated_data.get('last_name'),
            representative_code=validated_data.get('representative_code'),
            is_verified=True,
            is_active=True
        )
        # try:
        #     send_registration_otp_email(user)
        # except ValidationError as e:
        #     # If OTP sending fails, we still want to return the user
        #     # The frontend can handle retry logic
        #     pass
        return user


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def validate(self, attrs):
        email = attrs.get('email')
        otp = attrs.get('otp')

        user = User.objects.filter(email=email).first()
        if not user:
            raise serializers.ValidationError("User with this email does not exist.")

        if user.is_verified:
            raise serializers.ValidationError("This account is already verified.")

        otp_obj = EmailOTP.objects.filter(user=user).first()
        if not otp_obj or otp_obj.otp != otp:
            raise serializers.ValidationError("Invalid OTP.")

        # if otp_obj.is_expired():
        #     raise serializers.ValidationError("OTP has expired. Please request a new one.")

        # If we reach here, OTP is valid
        user.is_verified = True
        user.is_active = True
        user.save()

        # CLEAR THE OTP HERE
        otp_obj.delete()

        # Send welcome email via Celery
        from apps.account.tasks import send_welcome_email_task
        send_welcome_email_task.delay(
            user_email=user.email,
            first_name=user.first_name,
            last_name=user.last_name
        )

        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email or not password:
            raise serializers.ValidationError("Both email and password are required.")

        user = authenticate(request=self.context.get('request'), email=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated.")

        if not user.is_verified:
            # We raise a specific error so the frontend can redirect to Screen 3 (OTP)
            raise serializers.ValidationError("PENDING_VERIFICATION")

        # Standard JWT token generation
        tokens = get_tokens_for_user(user)

        user = UserSerializer(user).data  # Serialize user data to return in response

        # Return the user and tokens so the View can use them
        return {
            'success': True,
            'message': "User loged in successfully",
            'tokens': tokens,
            'user': user
        }


class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            self.user = User.objects.get(email=value, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        return value

    def save(self):
        try:
            send_forgot_password_otp_email(self.user)
        except ValidationError as e:
            raise serializers.ValidationError(str(e))

        return {"message": "OTP sent successfully"}


class ForgotPasswordVerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def validate(self, attrs):
        email = attrs["email"]
        otp = attrs["otp"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email.")

        otp_log = (
            EmailOTP.objects
            .filter(user=user, otp=otp)
            .order_by("-created_at")
            .first()
        )

        if not otp_log:
            raise serializers.ValidationError("Invalid OTP.")

        if not otp_log.otp_is_valid():
            raise serializers.ValidationError("OTP expired.")

        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(
        min_length=8,
        write_only=True
    )
    confirm_password = serializers.CharField(
        min_length=8,
        write_only=True
    )

    def validate(self, attrs):
        email = attrs.get("email")
        otp = attrs.get("otp")
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_password")

        if new_password != confirm_password:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        try:
            self.user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email.")

        otp_log = (
            EmailOTP.objects
            .filter(user=self.user, otp=otp)
            .order_by("-created_at")
            .first()
        )

        if not otp_log:
            raise serializers.ValidationError("Invalid OTP.")

        if not otp_log.otp_is_valid():
            raise serializers.ValidationError("OTP expired.")

        return attrs

    def save(self):
        self.user.set_password(self.validated_data["new_password"])
        self.user.save(update_fields=["password"])

        EmailOTP.objects.filter(user=self.user).delete()

        return {
            "message": "Password reset successful"
        }


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        current_password = attrs.get("current_password")
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_password")

        if new_password != confirm_password:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        if not self.context["request"].user.check_password(current_password):
            raise serializers.ValidationError({
                "current_password": "Incorrect current password."
            })

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        user.set_password(validated_data["new_password"])
        user.save(update_fields=["password"])
        return validated_data


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "avatar",
            "mobile_number",
            "is_active",
            "department",
            "job_title"
        )


class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = (
            "id",
            "address",
            "city",
            "state",
            "zip_code"
        )
        read_only_fields = ("id", "user")
