"""C integration host. SQLite and synthetic inputs require explicit local demo mode."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]
LOCAL_DEMO = os.environ.get('C_LOCAL_DEMO') == '1'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'local-demo-only' if LOCAL_DEMO else '')
if not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY is required')
DEBUG = LOCAL_DEMO
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
INSTALLED_APPS = ['django.contrib.contenttypes', 'django.contrib.sessions', 'rest_framework',
                  'backend.recommendation', 'backend.music']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware',
              'django.contrib.sessions.middleware.SessionMiddleware',
              'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware']
ROOT_URLCONF = 'backend.cafe.urls'
CSRF_FAILURE_VIEW = 'backend.recommendation.api.csrf_failure'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'local-demo.sqlite3'}} if LOCAL_DEMO else {
    'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': os.environ.get('PGDATABASE', ''),
                'USER': os.environ.get('PGUSER', ''), 'PASSWORD': os.environ.get('PGPASSWORD', ''),
                'HOST': os.environ.get('PGHOST', ''), 'PORT': os.environ.get('PGPORT', '5432')}}
USE_TZ = True
TIME_ZONE = 'UTC'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not LOCAL_DEMO
CSRF_COOKIE_SECURE = not LOCAL_DEMO
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
REST_FRAMEWORK = {'UNAUTHENTICATED_USER': None, 'DEFAULT_AUTHENTICATION_CLASSES': [],
                  'EXCEPTION_HANDLER': 'backend.recommendation.api.exception_handler'}
# A supplies an importable callable: (region_id, as_of) -> normalized bundle.
WEATHER_PROVIDER = os.environ.get('WEATHER_PROVIDER', '')
# B supplies ownership resolver (request -> opaque owner), event sink and shared guest bootstrap.
OWNER_RESOLVER = os.environ.get('OWNER_RESOLVER', '')
EVENT_SINK = os.environ.get('EVENT_SINK', '')
SEARCH_MAX_CANDIDATES = int(os.environ.get('SEARCH_MAX_CANDIDATES', '200' if LOCAL_DEMO else '0'))
SEARCH_SECONDS = float(os.environ.get('SEARCH_SECONDS', '10' if LOCAL_DEMO else '0'))
RECOMMENDATION_WORKER_IDLE_SECONDS = float(os.environ.get('RECOMMENDATION_WORKER_IDLE_SECONDS', '0.25' if LOCAL_DEMO else '1'))
GEMINI_ENABLED = os.environ.get('GEMINI_ENABLED') == '1'
GEMINI_TIMEOUT_MS = int(os.environ.get('GEMINI_TIMEOUT_MS', '0'))
GEMINI_MAX_CANDIDATES = int(os.environ.get('GEMINI_MAX_CANDIDATES', '0'))
# Known-video playback is keyless by default. Official search is an explicit option.
YOUTUBE_PLAYBACK_MODE = os.environ.get('YOUTUBE_PLAYBACK_MODE', 'KEYLESS')
if YOUTUBE_PLAYBACK_MODE not in {'KEYLESS', 'OPTIONAL_SEARCH'}:
    raise ImproperlyConfigured('YOUTUBE_PLAYBACK_MODE must be KEYLESS or OPTIONAL_SEARCH')
YOUTUBE_DATA_API_KEY = (os.environ.get('YOUTUBE_DATA_API_KEY') or os.environ.get('YOUTUBE_API_KEY') or '').strip()
YOUTUBE_SEARCH_TIMEOUT_SECONDS = float(os.environ.get('YOUTUBE_SEARCH_TIMEOUT_SECONDS') or '8')
YOUTUBE_SEARCH_PER_OWNER_MINUTE = int(os.environ.get('YOUTUBE_SEARCH_PER_OWNER_MINUTE') or '6')
YOUTUBE_SEARCH_DAILY_LIMIT = int(os.environ.get('YOUTUBE_SEARCH_DAILY_LIMIT') or '80')
YOUTUBE_SEARCH_CACHE_SECONDS = int(os.environ.get('YOUTUBE_SEARCH_CACHE_SECONDS') or '21600')
