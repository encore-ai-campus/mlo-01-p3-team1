import uuid
from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.module_loading import import_string
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from rest_framework.views import APIView, exception_handler as drf_exception_handler
from rest_framework.response import Response
from . import service, demo_feedback
from .errors import DomainError, require
from .models import Family, Job, Playlist
from .policy import GENRES, THEMES, OPTIONS
from .weather import obtain


def csrf_failure(request,reason=''):
    rid=str(uuid.uuid4())
    response=JsonResponse({'code':'CSRF_FAILED','message':'요청의 보안 정보를 새로 확인해 주세요.',
                           'details':{},'request_id':rid},status=403)
    response['X-Request-ID']=rid
    response['Cache-Control']='no-store'
    return response


def exception_handler(exc,context):
    rid=getattr(context['request'],'request_id',str(uuid.uuid4()))
    if isinstance(exc,DomainError):
        return Response({'code':exc.code,'message':exc.message,'details':exc.details,'request_id':rid},status=exc.status)
    result=drf_exception_handler(exc,context)
    if result is not None:
        result.data={'code':'VALIDATION_ERROR' if result.status_code==400 else 'REQUEST_FAILED',
                     'message':'요청을 처리할 수 없어요.','details':{},'request_id':rid}
        if result.status_code==400: result.status_code=422
    return result


@method_decorator(csrf_protect,name='dispatch')
class Endpoint(APIView):
    def initial(self,request,*args,**kwargs):
        request.request_id=str(uuid.uuid4())
        super().initial(request,*args,**kwargs)

    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['X-Request-ID']=getattr(request,'request_id',str(uuid.uuid4()))
        # Version disagreement is preserved; B integration must bind X-Contract-Version.
        response['Cache-Control']='no-store'
        response['X-Contract-Version']=settings.API_CONTRACT_VERSION
        return response

    def owner(self,request):
        if settings.OWNER_RESOLVER: return import_string(settings.OWNER_RESOLVER)(request)
        require(settings.LOCAL_DEMO,'POLICY_NOT_READY','익명 소유 서비스 연결을 기다리고 있어요.',503)
        if not request.session.get('c_demo_owner'):
            request.session['c_demo_owner']=str(uuid.uuid4())
        return request.session['c_demo_owner']

    def key(self,request): return request.headers.get('Idempotency-Key')


class Options(Endpoint):
    def get(self,request):
        return Response({'option_version':OPTIONS,'items':[
            *[{'code':k,'label':v,'type':'theme','enabled':True} for k,v in THEMES.items()],
            *[{'code':k,'label':v[0],'type':'genre','enabled':True} for k,v in GENRES.items()]]})


class DemoContext(Endpoint):
    def get(self,request):
        require(settings.LOCAL_DEMO,'NOT_FOUND','찾을 수 없어요.',404)
        self.owner(request)
        from backend.weather.regions import bundled,choice
        catalog=service.catalog()
        return Response({'is_test':True,'csrf_token':get_token(request),'regions':[choice(row) for row in bundled()],
                         'music_source':{'kind':'CSV' if catalog.source_ref.startswith('local-preview:') else 'SYNTHETIC',
                                         'catalog_version':catalog.version}})


class Weather(Endpoint):
    def get(self,request):
        if settings.WEATHER_PROVIDER == 'backend.weather.live.obtain':
            from backend.weather.live import display
            return Response(display(request.query_params.get('region_id'),timezone.now()))
        if settings.INTEGRATION_ENABLED and settings.WEATHER_PROVIDER == 'backend.weather.adapter.obtain':
            from backend.weather.adapter import display
            return Response(display(request.query_params.get('region_id'),timezone.now()))
        return Response(obtain(request.query_params.get('region_id'),timezone.now()))


class Jobs(Endpoint):
    def post(self,request):
        body,status=service.basic(self.owner(request),self.key(request),request.data,request.request_id)
        return Response(body,status=status)


class JobDetail(Endpoint):
    def get(self,request,pk):
        j=service.owned(Job,self.owner(request),pk)
        p=Playlist.objects.filter(job=j).first()
        error=None if j.error is None else {**j.error,'request_id':j.request_id}
        return Response({'job_id':j.pk,'status':j.status,'playlist_id':p.pk if p else None,'error':error})


class PlaylistDetail(Endpoint):
    def get(self,request,pk):
        p=service.owned(Playlist,self.owner(request),pk)
        f=p.family
        return Response({'playlist_id':p.pk,'family_id':f.pk,**p.snapshot,
                         'approval_revision':f.approval_revision,'approved_playlist_id':f.approved_playlist_id,
                         'exclusions_applied':set(p.snapshot['context']['excluded_track_ids'])==set(f.excluded)})


class Exclusions(Endpoint):
    def get(self,request,pk):
        value=service.exclusions(self.owner(request),pk)
        value['items']=[{k:t[k] for k in ['track_id','track_name','artists_name']} for t in value['items']]
        return Response(value)
    def put(self,request,pk):
        value,status=service.exclusions(self.owner(request),pk,self.key(request),request.data,request.request_id)
        return Response(value,status=status)


class Regenerate(Endpoint):
    def post(self,request,pk):
        value,status=service.regenerate(self.owner(request),pk,self.key(request),request.data,request.request_id)
        return Response(value,status=status)


class Approve(Endpoint):
    def post(self,request,pk):
        value,status=service.approve(self.owner(request),pk,self.key(request),request.data,request.request_id)
        return Response(value,status=status)


class WeatherRefresh(Endpoint):
    def post(self,request,pk):
        value,status=service.refresh_weather(self.owner(request),pk,self.key(request),request.data,request.request_id)
        return Response(value,status=status)


class Feedback(Endpoint):
    def get(self,request,pk):
        from backend.common import feedback
        handler = feedback if settings.INTEGRATION_ENABLED else demo_feedback
        return Response(handler.read(self.owner(request),pk))


class TrackReaction(Endpoint):
    def put(self,request,pk,track_id):
        from backend.common import feedback
        handler = feedback if settings.INTEGRATION_ENABLED else demo_feedback
        value,status=handler.save(self.owner(request),pk,'TRACK',track_id,
                                        request.data,self.key(request),request.request_id)
        return Response(value,status=status)


class PlaylistRating(Endpoint):
    def put(self,request,pk):
        from backend.common import feedback
        handler = feedback if settings.INTEGRATION_ENABLED else demo_feedback
        value,status=handler.save(self.owner(request),pk,'PLAYLIST','',
                                        request.data,self.key(request),request.request_id)
        return Response(value,status=status)
