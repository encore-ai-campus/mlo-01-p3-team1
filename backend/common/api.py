import hmac
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user
from django.middleware.csrf import get_token
from rest_framework.response import Response
from rest_framework.views import APIView
from backend.recommendation.api import Endpoint
from backend.recommendation.inputs import shape
from backend.recommendation.errors import require, DomainError
from .identity import admin, guest, raw_request
from .admin_roles import permitted, role_for
from .admin_dashboards import access_for, target_for


def account_data_for_user(user):
    active = user.is_authenticated and user.is_active and user.is_staff
    menus = []
    if active:
        for permission, path, label in [('manage_ads','/admin/ads','광고 관리'),
                ('manage_music','/admin/music','음악 관리'),
                ('manage_music','/admin/music/youtube','YouTube 연결 검수'),
                ('view_feedback','/admin/feedback/exclusions','제외 이력')]:
            if permitted(user, permission):
                menus.append({'path':path,'label':label})
        if target_for('operations') and permitted(user, 'view_operations'):
            menus.append({'path':'/api/admin/operations/kibana', 'label':'운영 대시보드'})
    return menus


def account_data(request):
    user = get_user(raw_request(request))
    active = user.is_authenticated and user.is_active and user.is_staff
    operations = access_for(user, 'operations')
    logs = access_for(user, 'logs')
    return {'authenticated':bool(active), 'role':'ADMIN' if active else None,
            'allowed_menus':account_data_for_user(user), 'csrf_token':get_token(raw_request(request)),
            'admin_role':role_for(user),
            'sso_enabled':settings.ADMIN_SSO_ENABLED,
            'local_login_enabled':settings.ADMIN_LOCAL_LOGIN_ENABLED,
            'operations_dashboard':operations, 'log_dashboard':logs,
            # Compatibility for the initial single-dashboard client.
            'kibana_dashboard':{**operations, 'path':'/api/admin/operations/kibana' if operations['path'] else None}}


class Me(Endpoint):
    def get(self, request):
        return Response(account_data(request))


class Login(Endpoint):
    def post(self, request):
        require(settings.ADMIN_LOCAL_LOGIN_ENABLED, 'SSO_REQUIRED', '통합 로그인으로 접속해 주세요.', 403)
        body = shape(request.data, ['username','password'], ['username','password'])
        require(all(type(body[k]) is str and body[k] for k in body))
        user = authenticate(raw_request(request), username=body['username'], password=body['password'])
        require(user is not None and user.is_active and user.is_staff,
                'AUTH_FAILED', '아이디 또는 비밀번호를 확인해 주세요.', 401)
        require(settings.ADMIN_SESSION_SECONDS > 0, 'POLICY_NOT_READY', '관리자 세션 만료 설정이 필요합니다.', 503)
        menus = account_data_for_user(user)
        require(bool(menus), 'FORBIDDEN', '사용 가능한 관리자 메뉴가 없습니다.', 403)
        login(raw_request(request), user)
        raw_request(request).session.set_expiry(settings.ADMIN_SESSION_SECONDS)
        return Response({**account_data(request), 'landing_path':menus[0]['path']})


class Logout(Endpoint):
    def post(self, request):
        shape(request.data, [])
        from .sso import logout_url
        target = logout_url(raw_request(request))
        logout(raw_request(request))
        return Response({'authenticated':False, 'logout_url':target})


class AdsContext(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # Internal service endpoint: bearer over TLS, never browser role/owner assertions.
        expected = settings.ADS_INTERNAL_SECRET
        supplied = request.headers.get('Authorization', '')
        require(bool(expected) and hmac.compare_digest(supplied.encode(), ('Bearer '+expected).encode()),
                'FORBIDDEN', '내부 서비스 인증이 필요합니다.', 403)
        body = shape(request.data, ['action','bootstrap'], ['action'])
        action = body['action']
        require(action in ('guest','admin'))
        if action == 'admin':
            user = admin(request, 'manage_ads')
            return Response({'account_id':str(user.pk),'identity_source':'common-postgresql',
                             'role':'ADMIN','active':True,'ads_allowed':True})
        require(type(body.get('bootstrap',False)) is bool)
        found = guest(request, bootstrap=body.get('bootstrap',False))
        return Response({'owner_guest_id':found.pk if found else None,
                         'measurement_available':bool(found and not getattr(raw_request(request),'_new_guest_token',None))})


class Health(Endpoint):
    def get(self, request):
        return Response({'status':'ok','database_verified':False})


class Regions(Endpoint):
    def get(self, request):
        try:
            from backend.weather.queries import search_regions, lookup_region
            from pipeline.weather.mapping_postgres import load_regions
            query=request.query_params.get('q','').strip()
            require(len(query)<=100)
            rows=search_regions(query) if query else load_regions()['entries']
            rows=[r for r in rows if r.get('mapping_status','mapped')=='mapped' and r.get('kind') in ('읍','면','동','리')]
            result=rows[:100]
            selected=request.query_params.get('region_id')
            if selected and not any(r['id']==selected for r in result):
                found=lookup_region(selected)
                if found is not None and found.get('mapping_status','mapped')=='mapped':
                    result=[found,*result[:99]]
            return Response({'items':[{'region_id':r['id'],'name':r.get('address',r['name']),
                                       'nx':r['nx'],'ny':r['ny']} for r in result],
                             'has_more':len(rows)>100})
        except DomainError:
            raise
        except Exception:
            raise DomainError('REGIONS_UNAVAILABLE','지역 매핑 저장소를 확인해 주세요.',503) from None


class RegionTree(Endpoint):
    def get(self,request):
        from backend.weather.regions import bundled,choice
        try:
            if settings.LOCAL_DEMO:
                rows=bundled();source='bundled_kma_mapping'
            else:
                from pipeline.weather.mapping_postgres import load_regions
                rows=load_regions()['entries'];source='postgresql_mapping'
            rows=[row for row in rows if row.get('kind') in ('읍','면','동','지역')
                  and row.get('mapping_status','mapped')=='mapped']
            items=sorted((choice(row) for row in rows),key=lambda row:(row['province'],row['district'],row['locality'],row['region_id']))
            return Response({'items':items,'source':source,'weather_is_test':not bool(settings.WEATHER_PROVIDER)})
        except Exception:
            raise DomainError('REGIONS_UNAVAILABLE','지역 계층 매핑을 확인해 주세요.',503) from None
