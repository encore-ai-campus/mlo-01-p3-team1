"""C integration host. SQLite and synthetic inputs require explicit local demo mode."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]
from pipeline.environment import load as load_service_env
load_service_env('common')
LOCAL_DEMO = os.environ.get('C_LOCAL_DEMO') == '1'
INTEGRATION_ENABLED = os.environ.get('INTEGRATION_ENABLED', '0' if LOCAL_DEMO else '1') == '1'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'local-demo-only' if LOCAL_DEMO else '')
if not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY is required')
DEBUG = LOCAL_DEMO
ALLOWED_HOSTS = [value.strip() for value in os.environ.get('DJANGO_ALLOWED_HOSTS','127.0.0.1,localhost,testserver').split(',') if value.strip()]
CSRF_TRUSTED_ORIGINS = [value.strip() for value in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS','').split(',') if value.strip()]
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'rest_framework',
                  'backend.recommendation', 'backend.music', 'backend.common']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware',
              'django.contrib.sessions.middleware.SessionMiddleware',
              'backend.common.identity.GuestCookieMiddleware',
              'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware']
ROOT_URLCONF = 'backend.cafe.urls'
CSRF_FAILURE_VIEW = 'backend.recommendation.api.csrf_failure'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': os.environ.get('C_LOCAL_DATABASE') or BASE_DIR / 'local-demo.sqlite3'}} if LOCAL_DEMO else {
    'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': os.environ.get('PGDATABASE', ''),
                'USER': os.environ.get('PGUSER', ''), 'PASSWORD': os.environ.get('PGPASSWORD', ''),
                'HOST': os.environ.get('PGHOST', ''), 'PORT': os.environ.get('PGPORT', '5432')}}
USE_TZ = True
if not LOCAL_DEMO:
    DATABASES['default']['OPTIONS']={'connect_timeout':int(os.environ.get('PGCONNECT_TIMEOUT','5')),**{key:os.environ[name] for key,name in
        [('sslmode','PGSSLMODE'),('sslrootcert','PGSSLROOTCERT')] if os.environ.get(name)}}
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
WEATHER_PROVIDER = os.environ.get('WEATHER_PROVIDER', 'backend.weather.adapter.obtain' if INTEGRATION_ENABLED else 'backend.weather.live.obtain')
KMA_LOCAL_CACHE_PATH = os.environ.get('KMA_LOCAL_CACHE_PATH', str(BASE_DIR / '.local/weather-live/latest.json'))
# B supplies ownership resolver (request -> opaque owner), event sink and shared guest bootstrap.
OWNER_RESOLVER = os.environ.get('OWNER_RESOLVER', 'backend.common.identity.owner' if INTEGRATION_ENABLED else '')
EVENT_SINK = os.environ.get('EVENT_SINK', 'backend.common.events.record' if INTEGRATION_ENABLED else '')
PASSWORD_HASHERS = ['backend.common.hashers.ServiceArgon2Hasher', 'django.contrib.auth.hashers.PBKDF2PasswordHasher']
GUEST_COOKIE_NAME = 'cafe_guest'
GUEST_TTL_SECONDS = int(os.environ.get('GUEST_TTL_SECONDS', '0'))
ADMIN_SESSION_SECONDS = int(os.environ.get('ADMIN_SESSION_SECONDS', '0'))
ADMIN_SSO_ENABLED = os.environ.get('ADMIN_SSO_ENABLED') == '1'
ADMIN_LOCAL_LOGIN_ENABLED = os.environ.get('ADMIN_LOCAL_LOGIN_ENABLED', '0' if ADMIN_SSO_ENABLED else '1') == '1'
ADMIN_SSO_ISSUER = os.environ.get('ADMIN_SSO_ISSUER', '').rstrip('/')
ADMIN_SSO_CLIENT_ID = os.environ.get('ADMIN_SSO_CLIENT_ID', '')
ADMIN_SSO_CLIENT_SECRET = os.environ.get('ADMIN_SSO_CLIENT_SECRET', '')
ADMIN_SSO_REDIRECT_URI = os.environ.get('ADMIN_SSO_REDIRECT_URI', '')
ADMIN_SSO_POST_LOGOUT_URI = os.environ.get('ADMIN_SSO_POST_LOGOUT_URI', '')
ADMIN_SSO_GROUPS_CLAIM = os.environ.get('ADMIN_SSO_GROUPS_CLAIM', 'groups')
ADMIN_SSO_KEYCLOAK_ADMIN_URL = os.environ.get('ADMIN_SSO_KEYCLOAK_ADMIN_URL', '').rstrip('/')
ADMIN_KIBANA_URL = os.environ.get('ADMIN_KIBANA_URL', '')
ADMIN_OPERATIONS_DASHBOARD_URL = os.environ.get('ADMIN_OPERATIONS_DASHBOARD_URL', '')
ADMIN_LOG_DASHBOARD_URL = os.environ.get('ADMIN_LOG_DASHBOARD_URL', '')
ADMIN_SSO_ELASTICSEARCH_URL = os.environ.get('ADMIN_SSO_ELASTICSEARCH_URL', '')
ADS_INTERNAL_SECRET = os.environ.get('ADS_INTERNAL_SECRET', '')
FEEDBACK_ENVELOPE_VERSION = 'phase3-20261014.1'
API_CONTRACT_VERSION = 'phase3-20261016.3'
CSV_UPLOAD_MAX_BYTES = int(os.environ.get('CSV_UPLOAD_MAX_BYTES','0'))
MUSIC_RAW_DIRECTORY = os.environ.get('MUSIC_RAW_DIRECTORY','')
MUSIC_S3_BUCKET = os.environ.get('MUSIC_S3_BUCKET','')
MUSIC_S3_REGION = os.environ.get('MUSIC_S3_REGION','')
MUSIC_S3_PREFIX = os.environ.get('MUSIC_S3_PREFIX','')
MUSIC_S3_ARCHIVE_DEFERRED = os.environ.get('MUSIC_S3_ARCHIVE_DEFERRED') == '1'
SEARCH_MAX_CANDIDATES = int(os.environ.get('SEARCH_MAX_CANDIDATES', '200' if LOCAL_DEMO else '0'))
SEARCH_SECONDS = float(os.environ.get('SEARCH_SECONDS', '10' if LOCAL_DEMO else '0'))
RECOMMENDATION_WORKER_IDLE_SECONDS = float(os.environ.get('RECOMMENDATION_WORKER_IDLE_SECONDS', '0.25' if LOCAL_DEMO else '1'))
RECOMMENDATION_QUEUE = os.environ.get('RECOMMENDATION_QUEUE', 'all')
RECOMMENDATION_WORKER_ID = os.environ.get('RECOMMENDATION_WORKER_ID', '')
RECOMMENDATION_LEASE_SECONDS = int(os.environ.get('RECOMMENDATION_LEASE_SECONDS', '30'))
RECOMMENDATION_HEARTBEAT_SECONDS = float(os.environ.get('RECOMMENDATION_HEARTBEAT_SECONDS', '10'))
RECOMMENDATION_JOB_TIMEOUT_SECONDS = int(os.environ.get('RECOMMENDATION_JOB_TIMEOUT_SECONDS', '180'))
RECOMMENDATION_MAX_RECOVERIES = int(os.environ.get('RECOMMENDATION_MAX_RECOVERIES', '2'))
RECOMMENDATION_MAX_QUEUED_RULE = int(os.environ.get('RECOMMENDATION_MAX_QUEUED_RULE', '100'))
RECOMMENDATION_MAX_QUEUED_GEMINI = int(os.environ.get('RECOMMENDATION_MAX_QUEUED_GEMINI', '20'))
GEMINI_MAX_CONCURRENT = int(os.environ.get('GEMINI_MAX_CONCURRENT', '1'))
GEMINI_MIN_INTERVAL_SECONDS = float(os.environ.get('GEMINI_MIN_INTERVAL_SECONDS', '2'))
GEMINI_ENABLED = os.environ.get('GEMINI_ENABLED') == '1'
GEMINI_TIMEOUT_MS = int(os.environ.get('GEMINI_TIMEOUT_MS', '0'))
GEMINI_MAX_CANDIDATES = int(os.environ.get('GEMINI_MAX_CANDIDATES', '0'))
# Known-video playback is keyless by default. Official search is an explicit option.
YOUTUBE_REGISTRY_BACKEND = os.environ.get('YOUTUBE_REGISTRY_BACKEND', 'local' if LOCAL_DEMO else 'disabled')
if YOUTUBE_REGISTRY_BACKEND not in {'local', 'database', 'disabled'}:
    raise ImproperlyConfigured('YOUTUBE_REGISTRY_BACKEND must be local, database or disabled')
YOUTUBE_PLAYBACK_MODE = os.environ.get('YOUTUBE_PLAYBACK_MODE', 'KEYLESS')
if YOUTUBE_PLAYBACK_MODE not in {'KEYLESS', 'OPTIONAL_SEARCH'}:
    raise ImproperlyConfigured('YOUTUBE_PLAYBACK_MODE must be KEYLESS or OPTIONAL_SEARCH')
YOUTUBE_DATA_API_KEY = (os.environ.get('YOUTUBE_DATA_API_KEY') or os.environ.get('YOUTUBE_API_KEY') or '').strip()
YOUTUBE_SEARCH_TIMEOUT_SECONDS = float(os.environ.get('YOUTUBE_SEARCH_TIMEOUT_SECONDS') or '8')
YOUTUBE_SEARCH_PER_OWNER_MINUTE = int(os.environ.get('YOUTUBE_SEARCH_PER_OWNER_MINUTE') or '6')
YOUTUBE_SEARCH_DAILY_LIMIT = int(os.environ.get('YOUTUBE_SEARCH_DAILY_LIMIT') or '80')
YOUTUBE_SEARCH_CACHE_SECONDS = int(os.environ.get('YOUTUBE_SEARCH_CACHE_SECONDS') or '21600')
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'recommendation_console': {'class': 'logging.StreamHandler'}},
    'loggers': {'recommendation.worker': {
        'handlers': ['recommendation_console'], 'level': 'INFO', 'propagate': False}},
}
