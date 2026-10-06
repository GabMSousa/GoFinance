from django.conf import settings


class SecurityHeadersMiddleware:
    """Add defense-in-depth headers without changing application responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()')
        if settings.CSP_POLICY:
            header = 'Content-Security-Policy-Report-Only' if settings.CSP_REPORT_ONLY else 'Content-Security-Policy'
            response.setdefault(header, settings.CSP_POLICY)
        return response
