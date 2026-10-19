"""Server-owned Kibana targets; Django gates navigation, Kibana gates data access."""
import re
from urllib.parse import parse_qsl, urlsplit
from django.conf import settings
from .admin_roles import permitted

PATHS = {'operations': '/api/admin/operations/dashboard', 'logs': '/api/admin/operations/logs'}
DASHBOARD_IDS = {'operations': 'music-operations-v1', 'logs': 'music-guest-behavior-v1'}
KIBANA_PATH = re.compile(r'/ops(?:/s/[A-Za-z0-9_-]{1,64})?/app/dashboards\Z')


def target_for(kind):
    if kind == 'operations':
        return settings.ADMIN_OPERATIONS_DASHBOARD_URL or settings.ADMIN_KIBANA_URL
    if kind == 'logs':
        return settings.ADMIN_LOG_DASHBOARD_URL
    raise ValueError('unknown_admin_dashboard')


def validated_target(kind):
    """Accept only configured HTTPS dashboard deep links in native-auth mode.

    Keep the old SSO-only (non-fragment) destination contract intact. This
    redirect is *never* a substitute for Kibana's own authentication/RBAC.
    """
    url = target_for(kind)
    if not isinstance(url, str) or not url or len(url) > 2048:
        return None
    if any(ord(char) < 32 or ord(char) == 127 or char == '\\' for char in url):
        return None
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 443)):
            return None
    except ValueError:
        return None

    # The already-deployed OIDC contract may use the IdP's login URL.
    if settings.ADMIN_SSO_ENABLED and not parsed.fragment:
        return url

    trusted = {host.strip().lower() for host in settings.ADMIN_KIBANA_ALLOWED_HOSTS if host.strip()}
    if parsed.hostname.lower() not in trusted or parsed.query or not KIBANA_PATH.fullmatch(parsed.path):
        return None

    route, delimiter, fragment_query = parsed.fragment.partition('?')
    if route != '/view/' + DASHBOARD_IDS[kind]:
        return None
    if delimiter:
        if not fragment_query or len(fragment_query) > 1024:
            return None
        try:
            parameters = parse_qsl(fragment_query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            return None
        if not parameters or any(key not in ('_g', '_a') for key, _ in parameters):
            return None
    return url


def access_for(user, kind):
    allowed = permitted(user, 'view_operations')
    configured = validated_target(kind) is not None
    return {'allowed': allowed, 'configured': configured,
            'path': PATHS[kind] if allowed and configured else None}
