from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin
)
from django.utils.safestring import mark_safe
from django.utils import timezone
from datetime import timedelta
import random
from apps.core.models import BaseModel


def user_image_upload_path(instance, filename):
    user_email = instance.email.replace("@", "_")
    return f"{user_email}/profile_image/{filename}"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email required")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    email = models.EmailField(unique=True)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    avatar = models.ImageField(upload_to=user_image_upload_path, null=True, blank=True)
    representative_code = models.CharField(max_length=20)

    job_title = models.CharField(max_length=100, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    mobile_number = models.CharField(max_length=20, null=True, blank=True)

    is_verified = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []   # required when creating superuser

    def __str__(self):
        return self.email
    
    def thumbnail(self):
        return mark_safe('<img src="/media/%s" width = "50" height = "50" />' % (self.avatar))


class EmailOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now=True)

    resend_after = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def generate_otp(self, length=6, resend_seconds=30, expire_minutes=10):
        code = ''.join(str(random.randint(0, 9)) for _ in range(length))
        
        now = timezone.now()
        self.otp = code
        self.created_at = now
        self.resend_after = now + timedelta(seconds=resend_seconds)
        self.expires_at = now + timedelta(minutes=expire_minutes)

        self.save(update_fields=['otp', 'created_at', 'resend_after', 'expires_at'])
        return code

    def otp_is_valid(self):
        if not self.otp or not self.expires_at:
            return False
        return timezone.now() <= self.expires_at

    def can_resend(self):
        if not self.resend_after:
            return True
        return timezone.now() >= self.resend_after

    def __str__(self):
        return f"OTP for {self.user.email} at {self.created_at}"
    

class ShippingAddress(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shipping_addresses')
    facility_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(max_length=150)
    contact_person = models.CharField(max_length=250, null=True, blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
