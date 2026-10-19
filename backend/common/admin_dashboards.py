"""Independent operations/log dashboard targets and server-owned access state."""
from urllib.parse import urlsplit
from django.conf import settings
from .admin_roles import permitted

PATHS = {'operations':'/api/admin/operations/dashboard', 'logs':'/api/admin/operations/logs'}


def target_for(kind):
    if kind == 'operations':
        return settings.ADMIN_OPERATIONS_DASHBOARD_URL or settings.ADMIN_KIBANA_URL
    if kind == 'logs':
        return settings.ADMIN_LOG_DASHBOARD_URL
    raise ValueError('unknown_admin_dashboard')


def access_for(user, kind):
    allowed = permitted(user, 'view_operations')
    try:
        target = urlsplit(target_for(kind))
        target.port  # Validate a configured port as well as the host.
        configured = bool(settings.ADMIN_SSO_ENABLED and target.scheme == 'https' and target.hostname
                          and not target.username and not target.password and not target.fragment)
    except ValueError:
        configured = False
    return {'allowed':allowed, 'configured':configured, 'path':PATHS[kind] if allowed and configured else None}
