from django.conf import settings


class LoginRequiredMiddleware:
    """Require an authenticated session for every application URL."""

    public_prefixes = ('/login/', '/admin/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(self.public_prefixes):
            from django.shortcuts import redirect
            from django.urls import reverse

            return redirect(f'{reverse("login")}?next={request.get_full_path()}')
        if request.user.is_authenticated and request.path not in {'/login/', '/senha/alterar/', '/logout/'}:
            from .models import UserSecurityProfile

            if UserSecurityProfile.objects.filter(user=request.user, must_change_password=True).exists():
                from django.shortcuts import redirect

                return redirect('/senha/alterar/')
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Add defense-in-depth headers without changing application responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            # Financial pages must never be reused by a shared browser/proxy cache.
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        response.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()')
        if settings.CSP_POLICY:
            header = 'Content-Security-Policy-Report-Only' if settings.CSP_REPORT_ONLY else 'Content-Security-Policy'
            response.setdefault(header, settings.CSP_POLICY)
        return response
