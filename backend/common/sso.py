"""OIDC authorization-code login; all redirects and issuers are server configured."""
import hashlib
import time
from urllib.parse import urlencode, urlsplit
from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.http import HttpResponseRedirect
from backend.recommendation.api import Endpoint
from backend.recommendation.errors import DomainError, require
from .admin_roles import ROLES, assign_role, role_for
from .identity import admin, raw_request
from .models import AdminSSOIdentity
from .admin_dashboards import target_for


def secure_url(value):
    parts = urlsplit(value)
    require(parts.scheme == 'https' and bool(parts.hostname) and not parts.username and not parts.password
            and not parts.fragment, 'SSO_NOT_CONFIGURED', '통합 로그인 HTTPS 설정을 확인해 주세요.', 503)
    return value


def oidc_client():
    require(settings.ADMIN_SSO_ENABLED and settings.ADMIN_SSO_CLIENT_ID and settings.ADMIN_SSO_CLIENT_SECRET,
            'SSO_NOT_CONFIGURED', '통합 로그인 연결을 기다리고 있습니다.', 503)
    issuer = secure_url(settings.ADMIN_SSO_ISSUER)
    secure_url(settings.ADMIN_SSO_REDIRECT_URI)
    secure_url(settings.ADMIN_SSO_POST_LOGOUT_URI)
    client = OAuth().register('admin_sso', client_id=settings.ADMIN_SSO_CLIENT_ID,
        client_secret=settings.ADMIN_SSO_CLIENT_SECRET,
        server_metadata_url=issuer + '/.well-known/openid-configuration',
        client_kwargs={'scope':'openid profile', 'code_challenge_method':'S256', 'default_timeout':5})
    metadata = client.load_server_metadata()
    require(metadata.get('issuer') == issuer, 'SSO_NOT_CONFIGURED', '인증 제공자 설정이 일치하지 않습니다.', 503)
    for key in ('authorization_endpoint', 'token_endpoint', 'jwks_uri', 'end_session_endpoint'):
        secure_url(metadata.get(key, ''))
    require('RS256' in metadata.get('id_token_signing_alg_values_supported', []),
            'SSO_NOT_CONFIGURED', '인증 제공자의 서명 설정을 확인해 주세요.', 503)
    client.server_metadata['id_token_signing_alg_values_supported'] = ['RS256']
    return client


def claims_role(claims):
    groups = claims.get(settings.ADMIN_SSO_GROUPS_CLAIM)
    require(isinstance(groups, list) and all(isinstance(item, str) for item in groups),
            'FORBIDDEN', '관리자 역할이 지정되지 않았습니다.', 403)
    roles = set(groups).intersection(ROLES)
    require(len(roles) == 1, 'FORBIDDEN', '관리자 역할은 하나만 지정해야 합니다.', 403)
    return roles.pop()


@transaction.atomic
def sync_identity(claims):
    role = claims_role(claims)
    issuer, subject = claims.get('iss'), claims.get('sub')
    require(issuer == settings.ADMIN_SSO_ISSUER and isinstance(subject, str) and 0 < len(subject) <= 255,
            'AUTH_FAILED', '인증 정보를 확인할 수 없습니다.', 401)
    # Never link accounts by email or preferred_username.
    identity = AdminSSOIdentity.objects.select_for_update().filter(issuer=issuer, subject=subject).first()
    if identity:
        user = get_user_model().objects.select_for_update().get(pk=identity.user_id)
        require(user.is_active, 'FORBIDDEN', '비활성화된 계정입니다.', 403)
    else:
        username = 'sso-' + hashlib.sha256((issuer + '\0' + subject).encode()).hexdigest()
        user = get_user_model()(username=username, is_active=True, is_staff=True)
        user.set_unusable_password()
        user.save()
        AdminSSOIdentity.objects.create(user=user, issuer=issuer, subject=subject)
    if role_for(user) != role:
        assign_role(user, role)
    return user


def logout_url(request):
    if not request.session.get('admin_sso'):
        return None
    try:
        from .sso_tokens import invalidate_kibana
        identity = AdminSSOIdentity.objects.get(user_id=request.session.get('_auth_user_id'))
        invalidate_kibana(identity.subject)
        client = oidc_client()
        endpoint = secure_url(client.load_server_metadata()['end_session_endpoint'])
        return endpoint + ('&' if '?' in endpoint else '?') + urlencode({
            'client_id':settings.ADMIN_SSO_CLIENT_ID,
            'post_logout_redirect_uri':settings.ADMIN_SSO_POST_LOGOUT_URI})
    except Exception:
        # Always clear the local session, even if the provider cannot be reached.
        return '/login?sso_logout=incomplete'


class SSOLogin(Endpoint):
    def get(self, request):
        try:
            response = oidc_client().authorize_redirect(raw_request(request), settings.ADMIN_SSO_REDIRECT_URI)
        except DomainError:
            raise
        except Exception:
            raise DomainError('SSO_UNAVAILABLE', '통합 로그인에 연결할 수 없습니다.', 503) from None
        return response


class SSOCallback(Endpoint):
    def get(self, request):
        try:
            client = oidc_client()
            token = client.authorize_access_token(raw_request(request), leeway=30,
                claims_options={'iss':{'essential':True, 'value':settings.ADMIN_SSO_ISSUER}})
            claims = token.get('userinfo')
            require(token.get('id_token') and claims and claims.get('exp', 0) > time.time(),
                    'AUTH_FAILED', '유효한 로그인 정보가 없습니다.', 401)
            require(settings.ADMIN_SESSION_SECONDS > 0, 'POLICY_NOT_READY', '관리자 세션 설정이 필요합니다.', 503)
            user = sync_identity(claims)
            login(raw_request(request), user, backend='django.contrib.auth.backends.ModelBackend')
            raw_request(request).session['admin_sso'] = True
            raw_request(request).session.set_expiry(min(settings.ADMIN_SESSION_SECONDS, int(claims['exp'] - time.time())))
            from .api import account_data_for_user
            return HttpResponseRedirect(account_data_for_user(user)[0]['path'])
        except DomainError:
            raise
        except Exception:
            raise DomainError('SSO_AUTH_FAILED', '통합 로그인에 실패했습니다. 다시 로그인해 주세요.', 401) from None


class KibanaDashboard(Endpoint):
    dashboard_kind = 'operations'

    def get(self, request):
        admin(request, 'view_operations')
        require(settings.ADMIN_SSO_ENABLED and raw_request(request).session.get('admin_sso'),
                'SSO_REQUIRED', '대시보드는 통합 로그인 후 이용해 주세요.', 403)
        return HttpResponseRedirect(secure_url(target_for(self.dashboard_kind)))


class OperationsDashboard(KibanaDashboard):
    dashboard_kind = 'operations'


class LogDashboard(KibanaDashboard):
    dashboard_kind = 'logs'
