import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

def env_bool(name, default=False):
    return os.environ.get(name, '1' if default else '0').strip().lower() in {'1', 'true', 'yes', 'on'}


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-only-change-me').strip()
DEBUG = env_bool('DJANGO_DEBUG', False)
if not DEBUG and SECRET_KEY in {'', 'dev-only-change-me', 'altere-para-uma-chave-forte'}:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set to a unique value when DJANGO_DEBUG=0.')
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        'DJANGO_CSRF_TRUSTED_ORIGINS',
        'http://localhost,http://127.0.0.1',
    ).split(',')
    if o.strip()
]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.environ.get('DJANGO_SECURE_REFERRER_POLICY', 'strict-origin-when-cross-origin')
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = env_bool('DJANGO_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('DJANGO_CSRF_COOKIE_SECURE', not DEBUG)
SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', False)
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = env_bool('DJANGO_SECURE_HSTS_PRELOAD', False)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'finance',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'finance.security.SecurityHeadersMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASE_ENGINE = os.environ.get('DJANGO_DB_ENGINE', 'sqlite').strip().lower()
if DATABASE_ENGINE in {'mysql', 'django.db.backends.mysql'}:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('MYSQL_DATABASE', 'saas_finance'),
            'USER': os.environ.get('MYSQL_USER', 'saas_finance'),
            'PASSWORD': os.environ.get('MYSQL_PASSWORD', ''),
            'HOST': os.environ.get('MYSQL_HOST', '127.0.0.1'),
            'PORT': os.environ.get('MYSQL_PORT', '3306'),
            'CONN_MAX_AGE': int(os.environ.get('MYSQL_CONN_MAX_AGE', '60')),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'connect_timeout': int(os.environ.get('MYSQL_CONNECT_TIMEOUT', '5')),
                'init_command': (
                    "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,"
                    "NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'"
                ),
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

VR_INITIAL_BALANCE = os.environ.get('VR_INITIAL_BALANCE', '0')
VR_MONTHLY_CREDIT = os.environ.get('VR_MONTHLY_CREDIT', '500')
REFERENCE_PREVIOUS_NET_SALARY = '2299.00'
REFERENCE_NEW_GROSS_SALARY = '3000.00'
DEFAULT_ADMIN_USERNAME = os.environ.get('DJANGO_ADMIN_USERNAME', 'gabriel.sousa')
DEFAULT_ADMIN_PASSWORD = os.environ.get('DJANGO_ADMIN_PASSWORD', '')
CSP_REPORT_ONLY = env_bool('DJANGO_CSP_REPORT_ONLY', True)
CSP_POLICY = os.environ.get(
    'DJANGO_CSP_POLICY',
    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
    "form-action 'self'; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "script-src 'self' https://cdn.jsdelivr.net; connect-src 'self'",
)
