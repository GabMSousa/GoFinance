from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailOrDefaultAdminBackend(ModelBackend):
    """Authenticate normal accounts by e-mail and only the default admin by username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None:
            return None

        identifier = username.strip()
        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=identifier).first()
        if user is None and identifier.casefold() == 'admin':
            user = user_model.objects.filter(username='admin', is_staff=True).first()
        if user is not None and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
