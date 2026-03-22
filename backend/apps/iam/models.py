import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _generate_username(self, email: str) -> str:
        base = email.split("@", 1)[0].strip() or "kuboard"
        return slugify(base)[:24] or f"user-{uuid.uuid4().hex[:8]}"

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")

        email = self.normalize_email(email)
        username = extra_fields.pop("username", "") or self._generate_username(email)

        if self.model.objects.filter(username=username).exists():
            username = f"{username}-{uuid.uuid4().hex[:6]}"

        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("display_name", "Kuboard Admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=128, blank=True)
    password_needs_reset = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.display_name or self.email


class UserGroup(models.Model):
    name = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=72, unique=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:72]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class UserGroupMembership(models.Model):
    user = models.ForeignKey(
        "iam.User",
        on_delete=models.CASCADE,
        related_name="group_memberships",
    )
    group = models.ForeignKey(
        "iam.UserGroup",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=32, default="member")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "group")
        ordering = ["group__name", "user__email"]

    def __str__(self):
        return f"{self.user} -> {self.group}"

