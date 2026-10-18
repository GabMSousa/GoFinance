from contextvars import ContextVar


_current_user = ContextVar('gofinance_current_user', default=None)


def get_current_user():
    user = _current_user.get()
    return user if getattr(user, 'is_authenticated', False) else None


def set_current_user(user):
    return _current_user.set(user if getattr(user, 'is_authenticated', False) else None)


def reset_current_user(token):
    _current_user.reset(token)


class UserOwnedManagerMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        user = get_current_user()
        return queryset.filter(owner=user) if user else queryset

    def create(self, **kwargs):
        user = get_current_user()
        if user and 'owner' not in kwargs:
            kwargs['owner'] = user
        return super().create(**kwargs)
