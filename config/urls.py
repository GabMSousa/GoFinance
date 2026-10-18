from django.contrib import admin
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.http import HttpRequest, HttpResponse
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import include, path


@ensure_csrf_cookie
def login_view(request: HttpRequest) -> HttpResponse:
    if request.method == 'GET' and request.GET.get('fresh') == '1' and request.user.is_authenticated:
        logout(request)
    return auth_views.LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True,
    )(request)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('finance.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
