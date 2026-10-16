"""Idempotent Kibana saved objects. No unsanitized data views or anonymous access."""
import base64
import json
from pathlib import Path
import sys
import urllib.request

ID='music-operations-v1'


def specification(aggs, dataset=None, mark='bar', encoding=None, transforms=None):
    body={'size':0,'aggs':aggs}
    # Dashboard time/filter placeholders are supported by Kibana's Vega Elasticsearch source.
    filters=['%dashboard_context-filter_clause%']
    if dataset:filters.append({'term':{'event.dataset':dataset}})
    body['query']={'bool':{'must':['%dashboard_context-must_clause%'],
      'must_not':['%dashboard_context-must_not_clause%'],
      'filter':filters+[{'range':{'@timestamp':{'%timefilter%':True}}}]}}
    spec={'$schema':'https://vega.github.io/schema/vega-lite/v5.json',
          'data':{'url':{'index':'ops-mlo-*','body':body},'format':{'property':'aggregations.rows.buckets'}},
          'mark':{'type':mark,'tooltip':True},'encoding':encoding or {
           'x':{'field':'key','type':'nominal','title':None,'axis':{'labelAngle':0}},
           'y':{'field':'doc_count','type':'quantitative','title':'건수'},
           'tooltip':[{'field':'key','title':'구분'},{'field':'doc_count','title':'건수'}]},
          'config':{'view':{'stroke':None}}}
    if mark == 'text':
        spec['mark'].update(fontSize=52, fontWeight='bold')
    if transforms:spec['transform']=transforms
    return spec


def objects():
    panels=[]
    def add(title,description,spec,w=24,h=12):
        index=len(panels);vid=ID+'-'+str(index+1)
        visual={'title':title,'description':description,'visState':json.dumps({'title':title,'type':'vega','params':{'spec':json.dumps(spec,ensure_ascii=False)},'aggs':[]}),
                'uiStateJSON':'{}','kibanaSavedObjectMeta':{'searchSourceJSON':'{}'}}
        panels.append((vid,visual,w,h))
    outcomes={'rows':{'terms':{'field':'ops.status','size':5}}}
    rate_rows={'rows':{'filters':{'filters':[{'match_all':{}}]},
                      'aggs':{'succeeded':{'filter':{'term':{'ops.status':'SUCCEEDED'}}}}}}
    add('추천 성공률 (%)','실제 비시험 카탈로그의 종료 작업: SUCCEEDED / (SUCCEEDED+FAILED+EXPIRED). 요청 생성시각 기준. 최근 7일 최대 5,000건 조회.',
        specification(rate_rows,'recommendation','text',{
          'text':{'field':'rate','type':'quantitative','format':'.1f'},
          'tooltip':[{'field':'succeeded.doc_count','title':'성공 작업'},{'field':'doc_count','title':'종료 작업'}]},
          [{'calculate':'datum.doc_count > 0 ? 100 * datum.succeeded.doc_count / datum.doc_count : null','as':'rate'}]),12,9)
    latency={'rows':{'filters':{'filters':[{'match_all':{}}]},'aggs':{'latency':{'percentiles':{'field':'ops.latency_seconds','percents':[95]}}}}}
    add('추천 응답 P95 (초)','작업 생성부터 결과 저장까지. 큐 대기 포함, 성공 작업에만 계산.',
        specification(latency,'recommendation','text',{'text':{'field':'p95','type':'quantitative','format':'.2f'}},
          [{'calculate':"datum.latency.values['95.0']",'as':'p95'}]),12,9)
    add('추천 결과 상태', '실패 원인은 아래 로그 검색에서 ops.error_type으로 확인합니다.',specification(outcomes,'recommendation'),24,9)
    add('날씨 수집 단계 성공 건수','한 요청이 API 수신·파싱·Kafka 발행에 각각 집계됩니다.',
        specification({'rows':{'filters':{'keyed':False,'filters':{
          'API 수신':{'term':{'ops.api_received':True}},'파싱':{'term':{'ops.parsed':True}},'Kafka 발행':{'term':{'ops.kafka_published':True}}}}}},'weather'),24,11)
    add('날씨 단계별 실패', 'collection / es_projection. Elasticsearch 실제 적재 실패를 포함합니다.',
        specification({'rows':{'terms':{'field':'ops.stage','size':10}}},None,encoding={
          'x':{'field':'key','type':'nominal','title':'단계'},'y':{'field':'doc_count','type':'quantitative','title':'실패 건수'}}),24,11)
    # The failure panel additionally filters outcome while preserving dashboard context.
    failure=json.loads(panels[-1][1]['visState'])
    spec=json.loads(failure['params']['spec']);spec['data']['url']['body']['query']['bool']['filter'] += [{'term':{'event.outcome':'failure'}},{'term':{'event.dataset':'weather'}}]
    failure['params']['spec']=json.dumps(spec,ensure_ascii=False);panels[-1][1]['visState']=json.dumps(failure)
    e2e={'rows':{'date_histogram':{'field':'@timestamp','fixed_interval':'10m','min_doc_count':1},
                  'aggs':{'latency':{'avg':{'field':'ops.pipeline_latency_seconds'}}}}}
    add('날씨 파이프라인 지연 (초)','수집 요청 시작 → 해당 request_id의 Spark ES 발행 완료. 배치 완료 기준이며 행별 지연과 다릅니다.',
        specification(e2e,'pipeline_latency','line',{'x':{'field':'key','type':'temporal','title':None},
          'y':{'field':'latency.value','type':'quantitative','title':'평균 초'}}),24,11)
    add('서버별 오류', '서비스·네이티브 파일·kernel·nginx에서 정규화한 error/fatal/critical 로그.',
        specification({'rows':{'terms':{'field':'host.name','size':20}}},None),24,11)
    error=json.loads(panels[-1][1]['visState']);spec=json.loads(error['params']['spec'])
    spec['data']['url']['body']['query']['bool']['filter'].append({'terms':{'log.level':['error','fatal','critical','severe','e','f']}})
    error['params']['spec']=json.dumps(spec,ensure_ascii=False);panels[-1][1]['visState']=json.dumps(error)
    latest={'rows':{'terms':{'field':'host.name','size':20},'aggs':{'last':{'max':{'field':'@timestamp'}},
                     'queue':{'top_hits':{'size':1,'sort':[{'@timestamp':'desc'}],'_source':['ops.queued_events','ops.active']}}}}}
    add('14대 수집기 마지막 수신 (분 전)','각 서버 60초 heartbeat. 차트가 없거나 3분을 넘으면 수집 중단을 점검하세요. Control B 중단 시 전체 수신이 지연됩니다.',
        specification(latest,'forwarder','bar',{'x':{'field':'key','type':'nominal','title':'서버','axis':{'labelAngle':-40}},
          'y':{'field':'minutes','type':'quantitative','title':'분 전'}},
          [{'calculate':'(now() - datum.last.value) / 60000','as':'minutes'}]),24,12)
    queue={'rows':{'terms':{'field':'host.name','size':20},'aggs':{'latest':{'top_hits':{'size':1,'sort':[{'@timestamp':'desc'}],'_source':['ops.queued_events']}}}}}
    add('서버별 로그 전송 대기','Filebeat pipeline active 이벤트. 로컬 disk queue 최대 512MB/대, 원본 보존.',
        specification(queue,'forwarder','bar',{'x':{'field':'key','type':'nominal','title':'서버','axis':{'labelAngle':-40}},
          'y':{'field':'pending','type':'quantitative','title':'대기 이벤트'}},
          [{'calculate':"datum.latest.hits.hits.length > 0 && datum.latest.hits.hits[0]._source.ops ? datum.latest.hits.hits[0]._source.ops.queued_events : null",'as':'pending'}]),24,12)
    latest_feedback={'rows':{'filters':{'filters':[{'match_all':{}}]},'aggs':{'latest':{'top_hits':{'size':1,'sort':[{'@timestamp':'desc'}],'_source':['ops.pending']}}}}}
    add('피드백 outbox 대기','PostgreSQL에서 SENT가 아닌 이벤트 수. 분당 읽기 전용 조회.',
        specification(latest_feedback,'feedback','text',{'text':{'field':'pending','type':'quantitative','format':',.0f'}},
          [{'calculate':"datum.latest.hits.hits.length > 0 && datum.latest.hits.hits[0]._source.ops ? datum.latest.hits.hits[0]._source.ops.pending : null",'as':'pending'}]),12,10)
    ads={'rows':{'terms':{'field':'ops.collection','size':5},'aggs':{'latest':{'top_hits':{'size':1,'sort':[{'@timestamp':'desc'}],'_source':['ops.count']}}}}}
    add('광고 MongoDB 원본 로그 수', '원본 저장 건수입니다. 운영 메타데이터만 복사하고 원본·스냅샷·이미지는 보존합니다.',
        specification(ads,'ads_audit','bar',{'x':{'field':'key','type':'nominal','title':'컬렉션'},
          'y':{'field':'stored','type':'quantitative','title':'보관 건수'}},
          [{'calculate':"datum.latest.hits.hits.length > 0 && datum.latest.hits.hits[0]._source.ops ? datum.latest.hits.hits[0]._source.ops.count : null",'as':'stored'}]),12,10)
    active={'rows':{'filters':{'filters':[{'range':{'@timestamp':{'gte':'now-3m'}}}]},
                    'aggs':{'hosts':{'cardinality':{'field':'host.name'}}}}}
    add('최근 3분 수신 서버 / 14대','14보다 작으면 미수신 서버를 점검하세요. 선택 시간 범위 안의 최근 3분입니다.',
        specification(active,'forwarder','text',{'text':{'field':'hosts.value','type':'quantitative','format':'d'},
          'color':{'condition':{'test':'datum.hosts.value < 14','value':'#bd271e'},'value':'#017d73'}}),24,9)
    refs=[];grid=[];objects=[];x=0;y=0;row_h=0
    for index,(vid,attrs,w,h) in enumerate(panels):
        if x+w>48:x=0;y+=row_h;row_h=0
        key='panel_'+str(index)
        refs.append({'type':'visualization','id':vid,'name':key})
        grid.append({'version':'8.19.23','type':'visualization','gridData':{'x':x,'y':y,'w':w,'h':h,'i':str(index+1)},
          'panelIndex':str(index+1),'embeddableConfig':{},'panelRefName':key})
        objects.append(('visualization',vid,attrs,[]));x+=w;row_h=max(row_h,h)
    objects.append(('dashboard',ID,{'title':'카페 음악 서비스 · 운영 관제','description':'날씨 데이터와 분리한 운영로그. 추천/날씨/Kafka/Spark/ES/DB/광고/14대 전송 상태.',
      'panelsJSON':json.dumps(grid),'optionsJSON':json.dumps({'useMargins':True,'hidePanelTitles':False}),
      'timeRestore':True,'timeFrom':'now-24h','timeTo':'now','refreshInterval':{'pause':False,'value':60000},
      'kibanaSavedObjectMeta':{'searchSourceJSON':json.dumps({'query':{'language':'kuery','query':''},'filter':[]})}},refs))
    return objects


def publish(config):
    auth='Basic '+base64.b64encode(('ops_admin:'+config['viewer_password']).encode()).decode()
    def request(method,path,body):
        req=urllib.request.Request('http://127.0.0.1:5601/ops'+path,data=json.dumps(body).encode(),
          headers={'Authorization':auth,'Content-Type':'application/json','kbn-xsrf':'observability'},method=method)
        with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)
    request('POST','/api/data_views/data_view',{'data_view':{'id':'music-ops-logs-v1','title':'ops-mlo-*','name':'Music operations logs','timeFieldName':'@timestamp'},'override':True})
    rows=objects()
    for kind,identity,attrs,refs in rows:
        value=request('POST','/api/saved_objects/'+kind+'/'+identity+'?overwrite=true',{'attributes':attrs,'references':refs})
        if value.get('error'):raise RuntimeError('saved_object_creation_failed')
    print(json.dumps({'dashboard_id':ID,'panels':len(rows)-1,'data_view':'ops-mlo-*','authentication':'required'}))


if __name__=='__main__':publish(json.loads(Path(sys.argv[1]).read_text()))
