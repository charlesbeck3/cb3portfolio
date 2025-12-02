from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    """Custom user model that extends Django's AbstractUser.
    This allows for future extension without requiring complex migrations.
    """
    pass
