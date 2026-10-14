"""격자별 최신 상태를 Elasticsearch에 반영. 원천·장기 이력 미저장."""
import json
import os
from datetime import datetime
from pathlib import Path
from weather.pipeline.common import KST
from weather.pipeline.service_view import enrich
from weather.pipeline.collection_logs import append as append_log, flush_if_configured
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from weather.pipeline.common import encode, normalize_event, OBS, FORECAST
from weather.pipeline.projection import project_grid


def request(base, method, path, body=None, raw=False):
    data=body if raw else encode(body) if body is not None else None
    req=Request(base+path, data=data, method=method,
                headers={'Content-Type':'application/x-ndjson' if raw else 'application/json'})
    with urlopen(req,timeout=60) as response:
        return json.load(response)


def ensure_index(base,index):
    # 인덱스는 인프라에서 미리 생성. 실행 중 스키마 자동 변경 없음.
    request(base,'GET','/'+index)


def newer(a,b):
    if (a['issued_at'],a['source_hash'])==(b['issued_at'],b['source_hash']):
        av=int(a['rule_version'].removeprefix('normalize_v'))
        bv=int(b['rule_version'].removeprefix('normalize_v'))
        if av!=bv:return av>bv
    return (a['issued_at'],a['received_at'],a['source_hash']) > (b['issued_at'],b['received_at'],b['source_hash'])


def trim_rows(rows):
    # 이전 완성 회차 + 최신 도착 회차만 유지. 학습용 이력 저장 아님.
    keep=[]
    for source,categories in [('odam',OBS),('vsrt',FORECAST)]:
        selected=[r for r in rows if r['source']==source]
        if not selected:continue
        key='target_at' if source=='odam' else 'issued_at'
        cohorts=sorted({r[key] for r in selected},reverse=True)
        ready=[]
        for cohort in cohorts:
            group=[r for r in selected if r[key]==cohort]
            targets={r['target_at'] for r in group}
            complete=all(set(categories)<={r['category'] for r in group if r['target_at']==t} for t in targets)
            if complete and (source=='odam' or len(targets)==6):ready.append(cohort)
        wanted={cohorts[0]}
        if ready:wanted.add(ready[0])
        keep.extend(r for r in selected if r[key] in wanted)
    # 예보 회차 교체 후에도 현재 시간 SKY가 사라지지 않게 최근 8개 대상 유지.
    sky_rows=[r for r in rows if r['source']=='vsrt' and r['category']=='SKY']
    targets=sorted({r['target_at'] for r in sky_rows},reverse=True)[:8]
    latest={}
    for row in sky_rows:
        target=row['target_at']
        if target in targets and (target not in latest or newer(row,latest[target])):
            latest[target]=row
    identities={r['_id'] for r in keep}
    keep.extend(r for r in latest.values() if r['_id'] not in identities)
    # 보완값도 대상별 최신 발표만, 최근 12개 대상만 유지.
    for source in ('shrt','KIMG'):
        selected=[r for r in rows if r['source']==source]
        targets=sorted({r['target_at'] for r in selected},reverse=True)[:12]
        latest={}
        for row in selected:
            key=(row['target_at'],row['category'])
            if row['target_at'] in targets and (key not in latest or newer(row,latest[key])):
                latest[key]=row
        keep.extend(latest.values())
    return keep


def merge_rows(previous,incoming):
    by_key={}
    for row in previous+incoming:
        key=(row['source'],row['issued_at'],row['target_at'],row['category'])
        if key not in by_key or newer(row,by_key[key]):by_key[key]=row
    return trim_rows(list(by_key.values()))


def write_batch(batch,batch_id,grid_broadcast,base,index):
    ensure_index(base,index)
    changed=defaultdict(list)
    normalized=batch.rdd.flatMap(lambda item:normalize_event(json.loads(item.value),grid_broadcast.value))
    for row in normalized.toLocalIterator():
        changed[(row['nx'],row['ny'])].append(row)
    all_rows=[row for values in changed.values() for row in values]
    grids=sorted(changed)
    for start in range(0,len(grids),50):
        group=grids[start:start+50]
        ids=[f'{nx}_{ny}' for nx,ny in group]
        old=request(base,'POST','/'+index+'/_mget',{'ids':ids})['docs']
        commands=[]
        for grid,item in zip(group,old):
            if item.get('error'):raise RuntimeError('latest_state_read_failed')
            previous=item.get('_source',{}).get('stream_state',{}).get('rows',[])
            rows=merge_rows(previous,changed[grid])
            view=enrich(project_grid(rows))
            view['stream_state']={'rows':rows}
            action={'_index':index,'_id':f'{grid[0]}_{grid[1]}'}
            if item.get('found'):
                action.update(if_seq_no=item['_seq_no'],if_primary_term=item['_primary_term'])
                operation='index'
            else: operation='create'
            commands.extend([encode({operation:action}),encode(view)])
        if commands:
            result=request(base,'POST','/_bulk',b'\n'.join(commands)+b'\n',raw=True)
            if result.get('errors'):raise RuntimeError('latest_view_write_failed')
    log_path=os.environ.get('WEATHER_PROCESS_LOG_PATH','')
    if log_path and all_rows:
        append_log(log_path,dict(stage='es_projection',ok=True,batch_id=batch_id,
                   normalized_rows=len(all_rows),grids=len(grids),
                   request_ids=sorted({r['request_id'] for r in all_rows if r.get('request_id')}),
                   requested_at=datetime.now(KST).isoformat()))
        flush_if_configured(log_path)
    print(json.dumps({'batch_id':batch_id,'normalized_rows':sum(len(v) for v in changed.values()),
                      'grids':len(grids),'sink':'elasticsearch_latest_only'}),flush=True)
