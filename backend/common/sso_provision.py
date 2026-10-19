"""Keycloak account lifecycle adapter. No calls occur until an explicit apply."""
import hashlib
import os
from urllib.parse import quote, urlsplit
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from .admin_roles import ROLES, assign_role, revoke_sessions
from .models import AdminSSOIdentity
from .sso import secure_url
from .sso_tokens import invalidate_kibana


class KeycloakAdmin:
    def __init__(self):
        self.base = secure_url(settings.ADMIN_SSO_KEYCLOAK_ADMIN_URL).rstrip('/')
        issuer = urlsplit(secure_url(settings.ADMIN_SSO_ISSUER))
        base = urlsplit(self.base)
        prefix, separator, realm = issuer.path.rpartition('/realms/')
        if not separator or not realm or '/' in realm or base.netloc != issuer.netloc or base.path != prefix + '/admin/realms/' + realm:
            raise ValueError('keycloak_admin_url_does_not_match_issuer')
        self.token = os.environ.get('ADMIN_SSO_PROVISION_TOKEN', '')
        if not self.token:
            raise ValueError('provision_token_required')

    def call(self, method, path, body=None):
        response = requests.request(method, self.base + path, json=body,
            headers={'Authorization':'Bearer ' + self.token}, timeout=10, allow_redirects=False)
        if response.status_code not in (200, 201, 204):
            raise ValueError('identity_provider_request_failed')
        return response.json() if response.content else None

    def find_user(self, username):
        users = self.call('GET', '/users?username=' + quote(username, safe='') + '&exact=true')
        if len(users) > 1:
            raise ValueError('ambiguous_identity')
        return users[0] if users else None

    def group(self, role):
        matches = self.call('GET', '/groups?search=' + role + '&exact=true')
        found = [group for group in matches if group['name'] == role and group.get('path') == '/' + role]
        if not found:
            self.call('POST', '/groups', {'name':role})
            return self.group(role)
        if len(found) != 1:
            raise ValueError('ambiguous_role_group')
        return found[0]['id']

    def set_role(self, user_id, role):
        path = '/users/' + quote(user_id, safe='')
        target = self.group(role)
        for group in self.call('GET', path + '/groups'):
            if group['name'] in ROLES:
                self.call('DELETE', path + '/groups/' + quote(group['id'], safe=''))
        self.call('PUT', path + '/groups/' + quote(target, safe=''))


def provision(username, role, action, password=None):
    if action not in ('create', 'set-role', 'revoke', 'reset-password') or (action in ('create', 'set-role') and role not in ROLES):
        raise ValueError('invalid_provision_request')
    if action in ('create', 'reset-password') and not password:
        raise ValueError('initial_password_required')
    client = KeycloakAdmin()
    remote = client.find_user(username)
    if remote is None:
        if action != 'create':
            raise ValueError('account_not_found')
        client.call('POST', '/users', {'username':username, 'enabled':False,
                    'attributes':{'cafe_managed':['true']}})
        remote = client.find_user(username)
    if not remote or remote.get('attributes', {}).get('cafe_managed') != ['true']:
        raise ValueError('unmanaged_identity_will_not_be_adopted')
    subject = remote['id']
    path = '/users/' + quote(subject, safe='')
    identity = AdminSSOIdentity.objects.filter(issuer=settings.ADMIN_SSO_ISSUER, subject=subject).first()
    if action != 'create' and identity is None:
        raise ValueError('local_binding_required')
    if action == 'create' and (remote.get('enabled') or (identity and identity.user.is_active)):
        raise ValueError('existing_account_use_explicit_update')
    was_active = bool(identity and identity.user.is_active and remote.get('enabled'))
    with transaction.atomic():
        if identity is None:
            name = 'sso-' + hashlib.sha256((settings.ADMIN_SSO_ISSUER + '\0' + subject).encode()).hexdigest()
            user = get_user_model()(username=name, is_active=False, is_staff=True)
            user.set_unusable_password()
            user.save()
            identity = AdminSSOIdentity.objects.create(user=user, issuer=settings.ADMIN_SSO_ISSUER, subject=subject)
        user = identity.user
        user.is_active = False
        user.save(update_fields=['is_active'])
        revoke_sessions(user)
    try:
        # Disable and expire IdP/Kibana sessions before changing any capability.
        client.call('PUT', path, {'enabled':False})
        client.call('POST', path + '/logout')
        invalidate_kibana(subject)
        if action == 'revoke':
            return {'status':'REVOKED', 'service':True, 'identity_provider':True}
        if action in ('create', 'set-role'):
            client.set_role(subject, role)
            with transaction.atomic():
                assign_role(user, role)
        if action in ('create', 'reset-password'):
            client.call('PUT', path + '/reset-password', {'type':'password', 'temporary':True, 'value':password})
        enabled = action == 'create' or was_active
        user.is_active = enabled
        user.save(update_fields=['is_active'])
        client.call('PUT', path, {'enabled':enabled})
        return {'status':'COMPLETE', 'service':True, 'identity_provider':True, 'active':enabled}
    except Exception:
        user.is_active = False
        user.save(update_fields=['is_active'])
        revoke_sessions(user)
        try:
            client.call('PUT', path, {'enabled':False})
            client.call('POST', path + '/logout')
        except Exception:
            raise ValueError('partial_failure_local_disabled_remote_recovery_required') from None
        raise ValueError('provision_failed_account_disabled') from None
