"""기본·SNO 전국 격자 및 KIM 구름량 영역 조회 계획."""
import math
from datetime import datetime,timedelta
from weather.pipeline.common import KST,UTC,OBS,FORECAST

def make_jobs(now,grids,kim_count,observation_delay_minutes=30,forecast_delay_minutes=30):
    # 첫 전체 시험은 공개 지연을 피하려 30분 여유. 운영 갱신 지연 실측과 별개.
    safe=now-timedelta(minutes=30)
    obs_safe=now-timedelta(minutes=observation_delay_minutes)
    fc_safe=now-timedelta(minutes=forecast_delay_minutes)
    obs=obs_safe.replace(minute=obs_safe.minute//10*10,second=0,microsecond=0)
    fc=fc_safe.replace(minute=30,second=0,microsecond=0)
    if fc>fc_safe: fc-=timedelta(hours=1)
    sno=safe.replace(hour=2,minute=0,second=0,microsecond=0)
    while sno>safe: sno-=timedelta(hours=3)
    while sno+timedelta(hours=3)<=safe: sno+=timedelta(hours=3)
    utc=now.astimezone(UTC)
    # KIM 계산/공개 지연 대비 6시간 이상 지난 회차. 실제 가용성은 응답 검사.
    kim=(utc-timedelta(hours=6)).replace(minute=0,second=0,microsecond=0)
    kim=kim.replace(hour=kim.hour//6*6)
    # 현재 시간 + 초단기 대상까지 매시간 구름량. 같은 발표·대상 요청은 재사용.
    kstart=utc.replace(minute=0,second=0,microsecond=0)
    kend=fc.astimezone(UTC).replace(minute=0)+timedelta(hours=6)
    jobs=[]
    for source,base,categories,hours in [('odam',obs,OBS,[0]),('vsrt',fc,FORECAST,list(range(1,7))),('shrt',sno,['SNO'],list(range(1,10)))]:
        for h in hours:
            target=base.replace(minute=0)+timedelta(hours=h) if source!='odam' else base
            for category in categories:
                params={'tmfc':base.strftime('%Y%m%d%H' if source=='shrt' else '%Y%m%d%H%M'),'vars':category}
                if source!='odam': params['tmef']=target.strftime('%Y%m%d%H')
                jobs.append(dict(name=f'{source}_{category}_{target:%Y%m%d%H%M}',source=source,category=category,endpoint=f'/api/typ01/cgi-bin/url/nph-dfs_{source}_grd',params=params))
    if kim_count not in (0, len(grids)):
        raise ValueError('kim_count_must_be_zero_or_all_grids')
    if kim_count:
        bounds = dict(lon1=math.floor((min(g['lon'] for g in grids)-0.15)*10)/10,
                      lat1=math.floor((min(g['lat'] for g in grids)-0.15)*10)/10,
                      lon2=math.ceil((max(g['lon'] for g in grids)+0.15)*10)/10,
                      lat2=math.ceil((max(g['lat'] for g in grids)+0.15)*10)/10)
        target = kstart
        while target <= kend:
            hf = int((target-kim).total_seconds()/3600)
            jobs.append(dict(name=f'KIMG_tcld_{target:%Y%m%d%H}',source='KIMG',category='TCDC',
                             response_format='kim_area_csv',endpoint='/api/typ06/url/nwp_nc_sfc2d_down.php',
                             params=dict(group='KIMG',vars='tcld',tmfc=kim.strftime('%Y%m%d%H'),
                                         hf=hf,dataType='CSV',help=1,**bounds)))
            target += timedelta(hours=1)
    return jobs
