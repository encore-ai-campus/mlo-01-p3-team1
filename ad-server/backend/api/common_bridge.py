"""별도 Django 호스트 사이의 공통 인증/guest 검증. 브라우저 역할값은 사용하지 않습니다."""
import json
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from django.conf import settings
from .ads_auth import AdminIdentity
from .ads_public_auth import PublicGuestContext
from domains.ads.errors import DomainError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def call_common(request,action,bootstrap=False):
    base=settings.ADS_COMMON_API_URL.rstrip('/')
    parsed=urlsplit(base)
    local=settings.DEBUG and parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1')
    if not settings.ADS_INTERNAL_SECRET or parsed.username or parsed.password or parsed.query or parsed.fragment or not (parsed.scheme=='https' or local):
        raise DomainError('AUTH_UNAVAILABLE','공통 인증 서비스 설정을 확인해 주세요.',503)
    cookie=request.headers.get('Cookie','')
    if len(cookie)>8192:raise DomainError('AUTH_REQUIRED','쿠키를 확인해 주세요.',401)
    message=Request(base+'/api/internal/ads-context',method='POST',
        data=json.dumps({'action':action,'bootstrap':bootstrap}).encode(),
        headers={'Authorization':'Bearer '+settings.ADS_INTERNAL_SECRET,'Cookie':cookie,'Content-Type':'application/json'})
    try:
        with build_opener(NoRedirect).open(message,timeout=5) as result:
            raw=result.read(65537)
            if len(raw)>65536:raise ValueError('oversized_auth_response')
            data=json.loads(raw);cookies=result.headers.get_all('Set-Cookie',[])
    except HTTPError as error:
        status=error.code if error.code in (401,403) else 503
        raise DomainError('AUTH_REQUIRED' if status==401 else 'FORBIDDEN' if status==403 else 'AUTH_UNAVAILABLE',
                          '공통 인증을 확인해 주세요.',status) from None
    except Exception:
        raise DomainError('AUTH_UNAVAILABLE','공통 인증 서비스에 연결할 수 없습니다.',503) from None
    def finalize(response):
        for value in cookies:
            response.cookies.load(value)
        return response
    return data,finalize


def authorize_admin(request,action):
    data,_=call_common(request,'admin')
    try:return AdminIdentity(**data)
    except Exception:raise DomainError('AUTH_UNAVAILABLE','관리자 인증 응답을 확인해 주세요.',503) from None


def resolve_guest(request,*,bootstrap):
    data,finalize=call_common(request,'guest',bootstrap)
    try:return PublicGuestContext(**data,response_finalizer=finalize)
    except Exception:raise DomainError('GUEST_UNAVAILABLE','방문자 문맥 응답을 확인해 주세요.',503) from None
