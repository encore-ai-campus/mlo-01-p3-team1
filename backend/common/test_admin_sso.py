import io
import json
import time
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch
import requests
from joserfc import jwt
from joserfc.jwk import RSAKey
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from .admin_roles import ROLES, assign_role, permitted, role_for
from .models import AdminSSOIdentity
from .sso_provision import provision, KeycloakAdmin

ISSUER = 'https://identity.example.org/realms/cafe'
SSO_SETTINGS = dict(LOCAL_DEMO=True, ADMIN_SSO_ENABLED=True, ADMIN_LOCAL_LOGIN_ENABLED=False,
    ADMIN_SSO_ISSUER=ISSUER, ADMIN_SSO_CLIENT_ID='cafe-web', ADMIN_SSO_CLIENT_SECRET='test-only-client',
    ADMIN_SSO_REDIRECT_URI='https://cafe.example.org/api/auth/sso/callback',
    ADMIN_SSO_POST_LOGOUT_URI='https://cafe.example.org/login', ADMIN_SSO_GROUPS_CLAIM='groups',
    ADMIN_SSO_KEYCLOAK_ADMIN_URL='https://identity.example.org/admin/realms/cafe',
    ADMIN_SSO_ELASTICSEARCH_URL='https://elastic.example.org:9200',
    ADMIN_KIBANA_URL='https://ops.example.org/login?auth_provider_hint=oidc1', ADMIN_SESSION_SECONDS=600)


@override_settings(**SSO_SETTINGS)
class AdminRoleTests(TestCase):
    def test_role_matrix_overrides_extra_direct_permissions_and_superuser_flag(self):
        for role, capabilities in ROLES.items():
            user = get_user_model().objects.create_user(role, password='test-password')
            assign_role(user, role)
            user.is_superuser = True
            user.save()
            user.user_permissions.add(*Permission.objects.filter(content_type__app_label='common'))
            self.assertEqual(role_for(user), role)
            for capability in ('manage_ads','manage_music','view_feedback','view_operations'):
                self.assertEqual(permitted(user, capability), capability in capabilities)
            self.client.force_login(user)
            me = self.client.get('/api/auth/me').json()
            self.assertEqual(me['admin_role'], role)
            paths = {item['path'] for item in me['allowed_menus']}
            self.assertEqual('/admin/ads' in paths, role != 'OPS_ADMIN')
            self.assertEqual('/api/admin/operations/kibana' in paths, role != 'ADS_ADMIN')
            if role == 'ADS_ADMIN':
                self.assertEqual(self.client.get('/api/admin/music/readiness').status_code, 403)
                self.assertEqual(self.client.get('/api/admin/operations/kibana').status_code, 403)

    def test_multiple_roles_or_inactive_account_fail_closed(self):
        user = get_user_model().objects.create_user('ambiguous')
        assign_role(user, 'SUPER_ADMIN')
        group, _ = Group.objects.get_or_create(name='ADS_ADMIN')
        user.groups.add(group)
        self.assertIsNone(role_for(user))
        self.assertFalse(permitted(user, 'manage_ads'))
        assign_role(user, 'OPS_ADMIN')
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['OPS_ADMIN'])
        user.is_active = False
        user.save()
        self.assertFalse(permitted(user, 'view_operations'))

    def test_role_change_revokes_local_sessions(self):
        user = get_user_model().objects.create_user('role-change')
        assign_role(user, 'SUPER_ADMIN')
        self.client.force_login(user)
        self.assertTrue(Session.objects.exists())
        assign_role(user, 'ADS_ADMIN')
        self.assertFalse(Session.objects.exists())

    def test_kibana_button_state_is_independent_of_link_configuration(self):
        for role in ROLES:
            user = get_user_model().objects.create_user('button-' + role)
            assign_role(user, role)
            self.client.force_login(user)
            allowed = role in ('SUPER_ADMIN', 'OPS_ADMIN')
            for url, enabled in (('',True),('http://ops.example.org',True),
                                 ('https://ops.example.org',False),('https://ops.example.org',True)):
                with self.subTest(role=role, url=url, sso=enabled), override_settings(ADMIN_KIBANA_URL=url,ADMIN_SSO_ENABLED=enabled):
                    access = self.client.get('/api/auth/me').json()['kibana_dashboard']
                    configured = enabled and url.startswith('https://')
                    self.assertEqual(access, {'allowed':allowed,'configured':configured,
                        'path':'/api/admin/operations/kibana' if allowed and configured else None})

    def test_local_password_cannot_bypass_sso_and_kibana_requires_sso_session(self):
        user = get_user_model().objects.create_user('local', password='test-password')
        assign_role(user, 'SUPER_ADMIN')
        self.assertEqual(self.client.post('/api/auth/login', {'username':'local','password':'test-password'}, content_type='application/json').status_code,403)
        self.client.force_login(user)
        self.assertEqual(self.client.get('/api/admin/operations/kibana').status_code,403)
        session = self.client.session
        session['admin_sso'] = True
        session.save()
        response = self.client.get('/api/admin/operations/kibana')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response['Location'],SSO_SETTINGS['ADMIN_KIBANA_URL'])

    def test_operations_and_logs_have_independent_targets_and_same_role_boundary(self):
        paths={'operations':'/api/admin/operations/dashboard','logs':'/api/admin/operations/logs'}
        for role in ROLES:
            user=get_user_model().objects.create_user('two-dashboards-'+role)
            assign_role(user,role)
            self.client.force_login(user)
            session=self.client.session
            session['admin_sso']=True
            session.save()
            for operations_url,logs_url in (('',''),('https://ops.example.org/dashboard',''),
                    ('','https://logs.example.org/dashboard'),('https://ops.example.org/dashboard','https://logs.example.org/dashboard')):
                with self.subTest(role=role,operations=operations_url,logs=logs_url), override_settings(
                        ADMIN_KIBANA_URL='',ADMIN_OPERATIONS_DASHBOARD_URL=operations_url,ADMIN_LOG_DASHBOARD_URL=logs_url):
                    me=self.client.get('/api/auth/me').json()
                    for kind,url in (('operations',operations_url),('logs',logs_url)):
                        allowed=role!='ADS_ADMIN'
                        self.assertEqual(me['operations_dashboard' if kind=='operations' else 'log_dashboard'],
                            {'allowed':allowed,'configured':bool(url),'path':paths[kind] if allowed and url else None})
                        response=self.client.get(paths[kind])
                        self.assertEqual(response.status_code,403 if not allowed else 302 if url else 503)
                        if allowed and url:self.assertEqual(response['Location'],url)


@override_settings(**SSO_SETTINGS)
class OIDCFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = RSAKey.generate_key(2048, parameters={'kid':'local-test'})

    def setUp(self):
        self.claim_overrides = {}
        self.tamper_token = False
        self.token_env = patch.dict('os.environ', {'ADMIN_SSO_ELASTIC_API_KEY':'test-only-key'})
        self.token_env.start()
        self.addCleanup(self.token_env.stop)
        self.token_posts = []
        self.mock_transport = patch('requests.sessions.Session.send', side_effect=self.send)
        self.mock_transport.start()
        self.addCleanup(self.mock_transport.stop)

    def send(self, request, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = request.url
        if request.url == ISSUER + '/.well-known/openid-configuration':
            data = {'issuer':ISSUER,'authorization_endpoint':ISSUER+'/authorize','token_endpoint':ISSUER+'/token',
                    'jwks_uri':ISSUER+'/keys','end_session_endpoint':ISSUER+'/logout',
                    'id_token_signing_alg_values_supported':['RS256']}
        elif request.url == ISSUER + '/keys':
            data = {'keys':[self.key.as_dict(private=False)]}
        elif request.url == ISSUER + '/token':
            self.token_posts.append(parse_qs(request.body))
            now = int(time.time())
            claims = {'iss':ISSUER,'sub':'subject-1','aud':'cafe-web','iat':now,'exp':now+300,
                      'nonce':self.nonce,'groups':['OPS_ADMIN'], **self.claim_overrides}
            data = {'access_token':'test-access','token_type':'Bearer','id_token':jwt.encode({'alg':'RS256','kid':'local-test'}, claims, self.key)}
            if self.tamper_token:
                data['id_token'] = data['id_token'].rsplit('.',1)[0] + '.c2lnbmF0dXJl'
        elif request.url == 'https://elastic.example.org:9200/_security/oauth2/token':
            self.assertEqual(request.method,'DELETE')
            self.assertEqual(json.loads(request.body), {'realm_name':'cafe_sso','username':'subject-1'})
            data = {'invalidated_tokens':2,'previously_invalidated_tokens':0,'error_count':0}
        else:
            raise AssertionError('Unexpected network request')
        response._content = json.dumps(data).encode()
        response.headers['Content-Type'] = 'application/json'
        return response

    def start(self):
        response = self.client.get('/api/auth/sso/login')
        self.assertEqual(response.status_code,302,response.content)
        query = parse_qs(urlsplit(response['Location']).query)
        self.state, self.nonce = query['state'][0], query['nonce'][0]
        self.assertEqual(query['code_challenge_method'],['S256'])
        return query

    def callback(self, state=None):
        return self.client.get('/api/auth/sso/callback', {'code':'test-code','state':state or self.state})

    def test_signed_login_pkce_binding_role_menu_logout_and_replay(self):
        self.start()
        response = self.callback()
        self.assertEqual(response.status_code,302,response.content)
        self.assertTrue(self.token_posts[0]['code_verifier'])
        identity = AdminSSOIdentity.objects.get(subject='subject-1')
        self.assertFalse(identity.user.has_usable_password())
        self.assertEqual(role_for(identity.user),'OPS_ADMIN')
        self.assertEqual(self.client.get('/api/admin/operations/kibana').status_code,302)
        self.assertEqual(self.callback().status_code,401)
        result = self.client.post('/api/auth/logout',{},content_type='application/json').json()
        self.assertTrue(result['logout_url'].startswith(ISSUER+'/logout?'))
        self.assertFalse(self.client.get('/api/auth/me').json()['authenticated'])

    def test_wrong_state_issuer_audience_expiry_nonce_and_roles_are_rejected(self):
        for claims in ({'iss':'https://other.example.org'}, {'aud':'other-client'}, {'exp':int(time.time())-120},
                       {'nonce':'wrong'}, {'groups':['SUPER_ADMIN','OPS_ADMIN']}, {'groups':['unknown']}):
            with self.subTest(claims=claims):
                self.claim_overrides = claims
                self.start()
                self.assertIn(self.callback().status_code,(401,403))
                self.assertFalse(AdminSSOIdentity.objects.exists())
        self.claim_overrides = {}
        self.start()
        self.assertEqual(self.callback('bad-state').status_code,401)

    def test_disabled_local_binding_is_not_reactivated_and_unverified_username_not_linked(self):
        existing = get_user_model().objects.create_user('same-name')
        self.claim_overrides = {'preferred_username':'same-name'}
        self.start()
        self.assertEqual(self.callback().status_code,302)
        identity = AdminSSOIdentity.objects.get()
        self.assertNotEqual(identity.user_id,existing.pk)
        identity.user.is_active=False
        identity.user.save()
        self.start()
        self.assertEqual(self.callback().status_code,403)

    def test_ads_sso_cannot_open_kibana_directly(self):
        self.claim_overrides={'groups':['ADS_ADMIN']}
        self.start()
        self.assertEqual(self.callback()['Location'],'/admin/ads')
        self.assertEqual(self.client.get('/api/admin/operations/kibana').status_code,403)

    def test_invalid_signature_and_insecure_provider_configuration_are_rejected(self):
        self.tamper_token=True
        self.start()
        self.assertEqual(self.callback().status_code,401)
        self.assertFalse(AdminSSOIdentity.objects.exists())
        with override_settings(ADMIN_SSO_ISSUER='http://identity.example.org/realms/cafe'):
            self.assertEqual(self.client.get('/api/auth/sso/login').status_code,503)

    def test_provider_unavailable_logout_still_clears_local_session(self):
        self.start()
        self.callback()
        with patch('backend.common.sso.oidc_client',side_effect=RuntimeError('secret-provider-detail')):
            response=self.client.post('/api/auth/logout',{},content_type='application/json')
        self.assertEqual(response.json()['logout_url'],'/login?sso_logout=incomplete')
        self.assertFalse(self.client.get('/api/auth/me').json()['authenticated'])


@override_settings(**SSO_SETTINGS)
class SSOProvisionTests(TestCase):
    def setUp(self):
        self.remote={'id':'remote-id','username':'operator','enabled':False,'attributes':{'cafe_managed':['true']}}
        self.invalidate=patch('backend.common.sso_provision.invalidate_kibana')
        self.invalidated=self.invalidate.start()
        self.addCleanup(self.invalidate.stop)
        self.provider=Mock()
        self.provider.find_user.return_value=self.remote
        self.factory=patch('backend.common.sso_provision.KeycloakAdmin',return_value=self.provider)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def test_one_command_creates_role_and_revocation_expires_both_sides(self):
        result=provision('operator','OPS_ADMIN','create','test-only-initial-password')
        self.assertEqual(result['status'],'COMPLETE')
        identity=AdminSSOIdentity.objects.get(subject='remote-id')
        self.assertTrue(identity.user.is_active)
        self.assertEqual(role_for(identity.user),'OPS_ADMIN')
        self.provider.set_role.assert_called_once_with('remote-id','OPS_ADMIN')
        self.client.force_login(identity.user)
        provision('operator',None,'revoke')
        identity.user.refresh_from_db()
        self.assertFalse(identity.user.is_active)
        self.assertFalse(Session.objects.exists())
        self.invalidated.assert_called_with('remote-id')
        self.assertTrue(any(call.args[:2]==('POST','/users/remote-id/logout') for call in self.provider.call.call_args_list))

    def test_partial_failure_keeps_account_disabled_and_does_not_report_success(self):
        self.provider.set_role.side_effect=RuntimeError('private-provider-response')
        with self.assertRaisesRegex(ValueError,'provision_failed_account_disabled'):
            provision('operator','SUPER_ADMIN','create','test-only-initial-password')
        self.assertFalse(AdminSSOIdentity.objects.get().user.is_active)

    def test_unmanaged_account_cannot_be_adopted(self):
        self.remote['attributes']={}
        with self.assertRaisesRegex(ValueError,'unmanaged_identity'):
            provision('operator','SUPER_ADMIN','create','test-only-initial-password')
        self.assertFalse(AdminSSOIdentity.objects.exists())

    def test_role_downgrade_revokes_sessions_and_replaces_capabilities(self):
        provision('operator','SUPER_ADMIN','create','test-only-initial-password')
        self.remote['enabled']=True
        user=AdminSSOIdentity.objects.get().user
        self.client.force_login(user)
        provision('operator','ADS_ADMIN','set-role')
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(role_for(user),'ADS_ADMIN')
        self.assertFalse(permitted(user,'view_operations'))
        self.assertFalse(Session.objects.exists())
        self.invalidated.assert_called_with('remote-id')

    def test_kibana_invalidation_failure_does_not_leave_enabled_local_account(self):
        self.invalidated.side_effect=RuntimeError('private-elastic-detail')
        with self.assertRaisesRegex(ValueError,'provision_failed_account_disabled'):
            provision('operator','OPS_ADMIN','create','test-only-initial-password')
        self.assertFalse(AdminSSOIdentity.objects.get().user.is_active)

    def test_dry_run_never_calls_provider_or_database_writes(self):
        with patch('backend.common.management.commands.provision_sso_admin.provision') as run:
            output=io.StringIO()
            call_command('provision_sso_admin','operator',role='OPS_ADMIN',stdout=output)
            self.assertFalse(json.loads(output.getvalue())['applied'])
            run.assert_not_called()

    def test_bootstrap_local_roles_and_production_requires_role(self):
        with override_settings(LOCAL_DEMO=False), patch.dict('os.environ',{'BOOTSTRAP_ADMIN_PASSWORD':'test-only-Password-123!'}):
            with self.assertRaisesRegex(CommandError,'explicit_admin_role_required'):
                call_command('bootstrap_admin','bad',permissions=['manage_ads'],stdout=io.StringIO())
            call_command('bootstrap_admin','local-role',role='ADS_ADMIN',stdout=io.StringIO())
        self.assertEqual(role_for(get_user_model().objects.get(username='local-role')),'ADS_ADMIN')

    def test_keycloak_adapter_rejects_other_realm_and_redirects(self):
        with patch.dict('os.environ',{'ADMIN_SSO_PROVISION_TOKEN':'test-only-provision-token'}):
            with override_settings(ADMIN_SSO_KEYCLOAK_ADMIN_URL='https://identity.example.org/admin/realms/other'):
                with self.assertRaisesRegex(ValueError,'does_not_match_issuer'):
                    KeycloakAdmin()
            client=KeycloakAdmin()
            reply=Mock(status_code=302)
            with patch('requests.request',return_value=reply) as send:
                with self.assertRaisesRegex(ValueError,'request_failed'):
                    client.call('GET','/users')
                self.assertFalse(send.call_args.kwargs['allow_redirects'])


@override_settings(
    LOCAL_DEMO=True,
    ADMIN_SSO_ENABLED=False,
    ADMIN_LOCAL_LOGIN_ENABLED=True,
    ADMIN_SESSION_SECONDS=600,
    ADMIN_KIBANA_ALLOWED_HOSTS=('d55cemi1yl53l.cloudfront.net',),
    ADMIN_KIBANA_URL='',
    ADMIN_OPERATIONS_DASHBOARD_URL='https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards'
        '#/view/music-operations-v1',
    ADMIN_LOG_DASHBOARD_URL='https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards'
        '#/view/music-guest-behavior-v1?_g=(filters:!())',
)
class NativeKibanaDashboardTests(TestCase):
    """Django and Kibana each enforce their own authentication boundaries."""

    def test_authorized_native_login_can_follow_both_exact_dashboard_links(self):
        for role in ('SUPER_ADMIN', 'OPS_ADMIN'):
            user = get_user_model().objects.create_user('native-' + role, password='test-password')
            assign_role(user, role)
            login_response = self.client.post(
                '/api/auth/login', {'username': user.username, 'password': 'test-password'},
                content_type='application/json')
            self.assertEqual(login_response.status_code, 200)
            me = self.client.get('/api/auth/me').json()
            self.assertEqual(me['admin_role'], role)
            for name, route in (('operations_dashboard', '/api/admin/operations/dashboard'),
                                ('log_dashboard', '/api/admin/operations/logs')):
                self.assertEqual(me[name], {'allowed': True, 'configured': True, 'path': route})
                response = self.client.get(route)
                self.assertEqual(response.status_code, 302)
                expected = (settings.ADMIN_OPERATIONS_DASHBOARD_URL if name == 'operations_dashboard'
                            else settings.ADMIN_LOG_DASHBOARD_URL)
                self.assertEqual(response['Location'], expected)
            self.client.post('/api/auth/logout', {}, content_type='application/json')

    def test_anonymous_ads_and_disabled_staff_are_denied_direct_urls(self):
        for route in ('/api/admin/operations/dashboard', '/api/admin/operations/logs'):
            self.assertEqual(self.client.get(route).status_code, 401)
        user = get_user_model().objects.create_user('ads-native')
        assign_role(user, 'ADS_ADMIN')
        self.client.force_login(user)
        me = self.client.get('/api/auth/me').json()
        for key in ('operations_dashboard', 'log_dashboard'):
            self.assertFalse(me[key]['allowed'])
            self.assertIsNone(me[key]['path'])
        for route in ('/api/admin/operations/dashboard', '/api/admin/operations/logs'):
            self.assertEqual(self.client.get(route).status_code, 403)
        user.is_active = False
        user.save()
        self.assertEqual(self.client.get('/api/admin/operations/dashboard').status_code, 401)

    def test_fail_closed_on_untrusted_or_malformed_deep_links(self):
        from django.conf import settings
        from .admin_dashboards import validated_target
        accepted = settings.ADMIN_LOG_DASHBOARD_URL
        self.assertEqual(validated_target('logs'), accepted)
        rejected = (
            'http://d55cemi1yl53l.cloudfront.net/ops/app/dashboards#/view/music-guest-behavior-v1',
            'https://evil.example.org/ops/app/dashboards#/view/music-guest-behavior-v1',
            'https://d55cemi1yl53l.cloudfront.net.evil.org/ops/app/dashboards#/view/music-guest-behavior-v1',
            'https://bad@d55cemi1yl53l.cloudfront.net/ops/app/dashboards#/view/music-guest-behavior-v1',
            'https://d55cemi1yl53l.cloudfront.net:444/ops/app/dashboards#/view/music-guest-behavior-v1',
            'https://d55cemi1yl53l.cloudfront.net/ops/login#/view/music-guest-behavior-v1',
            'https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards#/view/music-operations-v1',
            'https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards#/view/music-guest-behavior-v1/other',
            'https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards?next=https://evil.example.org'
                '#/view/music-guest-behavior-v1',
            'https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards'
                '#/view/music-guest-behavior-v1?evil=true',
            'https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards'
                '#/view/music-guest-behavior-v1\nLocation:https://evil.example.org',
        )
        for url in rejected:
            with self.subTest(url=url), override_settings(ADMIN_LOG_DASHBOARD_URL=url):
                self.assertIsNone(validated_target('logs'))
        with override_settings(ADMIN_KIBANA_ALLOWED_HOSTS=()):
            self.assertIsNone(validated_target('logs'))
            user = get_user_model().objects.create_user('ops-native')
            assign_role(user, 'OPS_ADMIN')
            self.client.force_login(user)
            self.assertFalse(self.client.get('/api/auth/me').json()['log_dashboard']['configured'])
            self.assertEqual(self.client.get('/api/admin/operations/logs').status_code, 503)
