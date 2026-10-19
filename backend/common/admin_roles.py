"""One managed role per account; capabilities are enforced on the server."""
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session

ROLES = {
    'SUPER_ADMIN': frozenset(('manage_ads', 'manage_music', 'view_feedback', 'view_operations')),
    'ADS_ADMIN': frozenset(('manage_ads',)),
    'OPS_ADMIN': frozenset(('manage_music', 'view_feedback', 'view_operations')),
}


def role_for(user):
    if not user.is_authenticated or not user.is_active or not user.is_staff:
        return None
    assigned = list(user.groups.filter(name__in=ROLES).values_list('name', flat=True))
    return assigned[0] if len(assigned) == 1 else None


def permitted(user, permission):
    if not user.is_authenticated or not user.is_active or not user.is_staff:
        return False
    role = role_for(user)
    if role:
        return permission in ROLES[role]
    # Keep old local fixtures/accounts usable; production requires one explicit role.
    legacy = settings.LOCAL_DEMO and not settings.ADMIN_SSO_ENABLED and not user.groups.filter(name__in=ROLES).exists()
    return bool(legacy and user.has_perm('common.' + permission))


def revoke_sessions(user):
    for session in Session.objects.iterator():
        if session.get_decoded().get('_auth_user_id') == str(user.pk):
            session.delete()


def assign_role(user, role):
    if role not in ROLES:
        raise ValueError('invalid_admin_role')
    permissions = list(Permission.objects.filter(content_type__app_label='common', codename__in=ROLES[role]))
    if len(permissions) != len(ROLES[role]):
        raise ValueError('run_migrations_first')
    group, _ = Group.objects.get_or_create(name=role)
    group.permissions.set(permissions)
    user.groups.set([group])
    user.user_permissions.clear()
    user.is_staff = True
    user.is_superuser = False
    user.save(update_fields=['is_staff', 'is_superuser'])
    revoke_sessions(user)
