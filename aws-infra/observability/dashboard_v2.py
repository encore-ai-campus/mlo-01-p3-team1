"""Twenty operational metrics, horizontal labels, and a cohesive Kibana layout.

Collector/application code is deliberately independent. Gauges use latest snapshots;
cumulative counters are never summed across snapshots. Publication uses optimistic locking.
"""
import base64
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

DASHBOARD_ID = 'music-operations-v1'
PREVIEW_ID = 'music-operations-v2-preview'
PREFIX = 'music-ops-v2-'
BLUE = '#536DFE'
TEAL = '#10B8A6'
RED = '#E65776'
AMBER = '#ECA43B'
INK = '#17243B'
MUTED = '#6B7C93'
FONT = 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif'
ERRORS = ['error', 'fatal', 'critical', 'severe', 'e', 'f']
STATUS_COLORS = {'domain': ['성공', '실패', '만료'], 'range': [TEAL, RED, AMBER]}


def query(dataset=None, filters=(), live=False, runtime=None):
    clauses = list(filters)
    if dataset:
        clauses.append({'term': {'event.dataset': dataset}})
    if live:
        clauses.append({'range': {'@timestamp': {'gte': 'now-3m', 'lte': 'now'}}})
        boolean = {'filter': clauses}
    else:
        boolean = {'must': ['%dashboard_context-must_clause%'],
                   'must_not': ['%dashboard_context-must_not_clause%'],
                   'filter': ['%dashboard_context-filter_clause%', *clauses,
                              {'range': {'@timestamp': {'%timefilter%': True}}}]}
    body = {'size': 0, 'query': {'bool': boolean}}
    if runtime:
        body['runtime_mappings'] = runtime
    return body


def source(body, aggs, prop='aggregations.rows.buckets'):
    return {'url': {'index': 'ops-mlo-*', 'body': {**body, 'aggs': aggs}},
            'format': {'property': prop}}


def bucket(aggs=None):
    return {'rows': {'filters': {'filters': [{'match_all': {}}]}, 'aggs': aggs or {}}}


def latest(fields):
    return {'top_hits': {'size': 1, 'sort': [{'@timestamp': 'desc'}], '_source': fields}}


def latest_value(field, name='latest'):
    # Empty responses and absent forwarder fields are unknown, not zero.
    return (f"datum.{name}.hits.hits.length && datum.{name}.hits.hits[0]._source.ops"
            f" && isValid(datum.{name}.hits.hits[0]._source.ops.{field})"
            f" ? datum.{name}.hits.hits[0]._source.ops.{field} : null")


def chart(title, subtitle, data, mark, encoding, transforms=(), empty='선택 기간에 해당하는 데이터가 없습니다'):
    return {'$schema': 'https://vega.github.io/schema/vega-lite/v5.json',
            'width': 'container', 'height': 'container',
            'autosize': {'type': 'fit', 'contains': 'padding', 'resize': True},
            'padding': {'left': 10, 'right': 20, 'top': 12, 'bottom': 10},
            'title': {'text': title, 'subtitle': subtitle, 'anchor': 'start',
                      'font': FONT, 'fontSize': 16, 'fontWeight': 650, 'color': INK,
                      'subtitleFont': FONT, 'subtitleFontSize': 11, 'subtitleColor': MUTED,
                      'subtitlePadding': 8, 'offset': 18},
            'data': data, 'transform': list(transforms),
            'layer': [{'mark': mark, 'encoding': encoding},
                      {'transform': [{'aggregate': [{'op': 'count', 'as': '_rows'}]},
                                     {'filter': 'datum._rows === 0'}],
                       'mark': {'type': 'text', 'font': FONT, 'fontSize': 12, 'color': MUTED,
                                'align': 'left'},
                       'encoding': {'x': {'value': 8}, 'y': {'value': 28}, 'text': {'value': empty}}}],
            'config': {'font': FONT, 'background': 'white', 'view': {'stroke': None},
                       'axis': {'labelAngle': 0, 'labelColor': MUTED, 'labelFontSize': 10,
                                'labelPadding': 8, 'titleColor': MUTED, 'titleFontSize': 10,
                                'titlePadding': 12, 'domain': False, 'ticks': False,
                                'gridColor': '#EBF0F7', 'gridOpacity': 0.8},
                       'axisX': {'labelAngle': 0, 'labelOverlap': 'greedy', 'labelFlush': True,
                                 'labelBound': True, 'tickCount': 6},
                       'axisY': {'labelAngle': 0, 'labelLimit': 215},
                       'legend': {'orient': 'bottom', 'title': None, 'labelColor': MUTED,
                                  'labelFontSize': 10, 'symbolType': 'circle', 'padding': 10},
                       'range': {'category': [BLUE, TEAL, AMBER, RED, '#9B83E8', '#2196D2', '#78A541', '#BB6A9A']}}}


def horizontal(title, subtitle, data, transforms=(), value='doc_count', label='key', color=BLUE,
               extra_encoding=None, empty='선택 기간에 해당하는 데이터가 없습니다'):
    encoding = {'y': {'field': label, 'type': 'nominal', 'sort': '-x', 'title': None,
                      'axis': {'labelAngle': 0, 'grid': False}},
                'x': {'field': value, 'type': 'quantitative', 'title': '건수',
                      'axis': {'labelAngle': 0, 'format': '~s'}},
                'tooltip': [{'field': label, 'title': '구분'},
                            {'field': value, 'type': 'quantitative', 'title': '건수', 'format': ',.0f'}]}
    encoding.update(extra_encoding or {})
    return chart(title, subtitle, data,
                 {'type': 'bar', 'cornerRadiusEnd': 4, 'height': {'band': 0.62}, 'color': color},
                 encoding, transforms, empty)


def percentile_trend(title, subtitle, dataset, field, filters=()):
    aggs = {'rows': {'date_histogram': {'field': '@timestamp', 'fixed_interval': '10m', 'min_doc_count': 1},
                     'aggs': {'latency': {'percentiles': {'field': field, 'percents': [50, 95]}}}}}
    transforms = [{'calculate': "datum.latency.values['50.0']", 'as': 'P50'},
                  {'calculate': "datum.latency.values['95.0']", 'as': 'P95'},
                  {'fold': ['P50', 'P95'], 'as': ['percentile', 'seconds']},
                  {'filter': 'isValid(datum.seconds)'}]
    return chart(title, subtitle, source(query(dataset, filters), aggs),
                 {'type': 'line', 'strokeWidth': 2.5, 'point': {'filled': True, 'size': 15}},
                 {'x': {'field': 'key', 'type': 'temporal', 'title': None,
                        'axis': {'labelAngle': 0, 'format': '%H:%M', 'tickCount': 5}},
                  'y': {'field': 'seconds', 'type': 'quantitative', 'title': '초', 'scale': {'zero': True}},
                  'color': {'field': 'percentile', 'type': 'nominal',
                            'scale': {'domain': ['P50', 'P95'], 'range': [TEAL, BLUE]}},
                  'tooltip': [{'field': 'key', 'type': 'temporal', 'title': '시간'},
                              {'field': 'percentile', 'title': '백분위'},
                              {'field': 'seconds', 'type': 'quantitative', 'title': '초', 'format': '.2f'}]}, transforms)


def card(title, subtitle, data, expression, unit='', fmt=',.0f', color=BLUE, warning=None, transforms=()):
    value = "data('metric').length ? (" + expression + ') : null'
    display = "isValid(value) ? format(value, '" + fmt + "') + '" + unit + "' : '—'"
    return {'$schema': 'https://vega.github.io/schema/vega/v5.json', 'padding': 0,
            'data': [{'name': 'metric', **data, 'transform': list(transforms)}],
            'signals': [{'name': 'value', 'update': value},
                        {'name': 'accent', 'update': warning or json.dumps(color)},
                        {'name': 'display', 'update': display}],
            'marks': [
                {'type': 'rect', 'encode': {'update': {'x': {'value': 1}, 'y': {'value': 1},
                    'width': {'signal': 'width-2'}, 'height': {'signal': 'height-2'},
                    'fill': {'value': '#F7F9FD'}, 'stroke': {'value': '#E7ECF5'}, 'cornerRadius': {'value': 12}}}},
                {'type': 'rect', 'encode': {'update': {'x': {'value': 18}, 'y': {'value': 19},
                    'width': {'value': 22}, 'height': {'value': 4}, 'fill': {'signal': 'accent'}, 'cornerRadius': {'value': 2}}}},
                {'type': 'text', 'encode': {'update': {'x': {'value': 18}, 'y': {'value': 44},
                    'text': {'value': title}, 'font': {'value': FONT}, 'fontSize': {'value': 12},
                    'fontWeight': {'value': 600}, 'fill': {'value': MUTED}, 'limit': {'signal': 'width-30'}}}},
                {'type': 'text', 'encode': {'update': {'x': {'value': 18}, 'y': {'signal': 'height * 0.62'},
                    'text': {'signal': 'display'}, 'font': {'value': FONT},
                    'fontSize': {'signal': 'clamp(width/6,26,40)'}, 'fontWeight': {'value': 700},
                    'fill': {'signal': 'accent'}, 'limit': {'signal': 'width-30'}}}},
                {'type': 'text', 'encode': {'update': {'x': {'value': 18}, 'y': {'signal': 'height-17'},
                    'text': {'value': subtitle}, 'font': {'value': FONT}, 'fontSize': {'value': 10},
                    'fill': {'value': MUTED}, 'limit': {'signal': 'width-28'}}}}]}


def banner(title, subtitle, label='OPERATIONS', hero=False):
    bg = '#101C31' if hero else '#F3F6FC'
    return {'$schema': 'https://vega.github.io/schema/vega/v5.json', 'padding': 0,
            'marks': [
                {'type': 'rect', 'encode': {'update': {'width': {'signal': 'width'}, 'height': {'signal': 'height'},
                    'fill': {'value': bg}, 'cornerRadius': {'value': 10}}}},
                {'type': 'rect', 'encode': {'update': {'x': {'value': 20}, 'y': {'value': 15},
                    'width': {'value': 4}, 'height': {'signal': 'height-30'}, 'fill': {'value': TEAL}, 'cornerRadius': {'value': 2}}}},
                {'type': 'text', 'encode': {'update': {'x': {'value': 40}, 'y': {'value': 25 if hero else 22},
                    'text': {'value': label if hero else title}, 'font': {'value': FONT},
                    'fontSize': {'value': 10 if hero else 17}, 'fontWeight': {'value': 700},
                    'fill': {'value': '#7FE2D6' if hero else INK}, 'limit': {'signal': 'width-75'}}}},
                {'type': 'text', 'encode': {'update': {'x': {'value': 40}, 'y': {'value': 58 if hero else 44},
                    'text': {'value': title if hero else subtitle}, 'font': {'value': FONT},
                    'fontSize': {'value': 27 if hero else 11}, 'fontWeight': {'value': 700 if hero else 400},
                    'fill': {'value': 'white' if hero else MUTED}, 'limit': {'signal': 'width-75'}}}},
                *([{'type': 'text', 'encode': {'update': {'x': {'value': 40}, 'y': {'value': 83},
                    'text': {'value': subtitle}, 'font': {'value': FONT}, 'fontSize': {'value': 11},
                    'fill': {'value': '#A9B9D4'}, 'limit': {'signal': 'width-75'}}}}] if hero else [])]}


def heading_marks(title, subtitle):
    return [{'type': 'text', 'encode': {'update': {'x': {'value': 12}, 'y': {'value': y},
             'text': {'value': text}, 'font': {'value': FONT}, 'fontSize': {'value': size},
             'fontWeight': {'value': weight}, 'fill': {'value': color}, 'limit': {'signal': 'width-24'}}}}
            for text, y, size, weight, color in [(title, 26, 16, 650, INK), (subtitle, 49, 11, 400, MUTED)]]


def service_state_spec(data):
    return {'$schema': 'https://vega.github.io/schema/vega/v5.json', 'padding': 0,
            'data': [{'name': 'hosts', **data},
                     {'name': 'all_units', 'source': 'hosts', 'transform': [
                         {'type': 'flatten', 'fields': ['units.buckets'], 'as': ['unit']},
                         {'type': 'formula', 'as': 'state', 'expr': "datum.unit.latest.hits.hits.length ? datum.unit.latest.hits.hits[0]._source.ops.state : null"},
                         {'type': 'filter', 'expr': "isValid(datum.state) && datum.state !== 'active'"},
                         {'type': 'formula', 'as': 'label', 'expr': "datum.key + ' · ' + replace(datum.unit.key, 'music-', '')"}]},
                     {'name': 'units', 'source': 'all_units', 'transform': [
                         {'type': 'window', 'ops': ['row_number'], 'as': ['row']},
                         {'type': 'filter', 'expr': 'datum.row <= 12'}]}],
            'scales': [{'name': 'rows', 'type': 'band', 'domain': {'data': 'units', 'field': 'label'},
                        'range': [76, {'signal': 'height-35'}], 'padding': 0.2},
                       {'name': 'state_color', 'type': 'ordinal',
                        'domain': ['failed', 'inactive', 'activating', 'deactivating'],
                        'range': [RED, MUTED, AMBER, AMBER]}],
            'marks': [*heading_marks('비활성 서비스 점검 · LIVE', '최근 3분 수신 unit · inactive는 의도된 중지일 수 있습니다'),
                      {'type': 'text', 'encode': {'update': {
                          'x': {'signal': 'width/2'}, 'y': {'signal': 'height/2'}, 'align': {'value': 'center'},
                          'font': {'value': FONT}, 'fontSize': {'value': 13},
                          'fill': {'signal': f"length(data('hosts')) ? '{TEAL}' : '{MUTED}'"},
                          'text': {'signal': "length(data('hosts')) ? '수신한 서비스 중 비활성 항목이 없습니다' : '서비스 상태를 수신하지 못했습니다'"},
                          'opacity': {'signal': "length(data('all_units')) ? 0 : 1"}}}},
                      {'type': 'rect', 'from': {'data': 'units'}, 'encode': {'update': {
                          'x': {'value': 12}, 'width': {'signal': 'width-24'},
                          'y': {'scale': 'rows', 'field': 'label'}, 'height': {'scale': 'rows', 'band': 1},
                          'fill': {'value': '#F3F6FC'}, 'cornerRadius': {'value': 5}}}},
                      {'type': 'text', 'from': {'data': 'units'}, 'encode': {'update': {
                          'x': {'value': 22}, 'y': {'scale': 'rows', 'field': 'label', 'band': 0.5},
                          'baseline': {'value': 'middle'}, 'font': {'value': FONT}, 'fontSize': {'value': 11},
                          'fill': {'value': INK}, 'text': {'field': 'label'}, 'limit': {'signal': 'width-150'},
                          'tooltip': {'signal': "{'서비스':datum.label,'상태':datum.state}"}}}},
                      {'type': 'text', 'from': {'data': 'units'}, 'encode': {'update': {
                          'x': {'signal': 'width-26'}, 'y': {'scale': 'rows', 'field': 'label', 'band': 0.5},
                          'align': {'value': 'right'}, 'baseline': {'value': 'middle'}, 'font': {'value': FONT},
                          'fontSize': {'value': 11}, 'fontWeight': {'value': 600}, 'text': {'field': 'state'},
                          'fill': {'scale': 'state_color', 'field': 'state'}}}},
                      {'type': 'text', 'encode': {'update': {'x': {'value': 12}, 'y': {'signal': 'height-12'},
                          'fontSize': {'value': 10}, 'fill': {'value': MUTED},
                          'text': {'signal': "length(data('all_units')) > 12 ? '총 '+length(data('all_units'))+'개 중 12개 표시' : ''"}}}}]}


def ads_integrity_spec(data):
    names = "datum.key === 'ad_admin_changes' ? '관리 변경' : datum.key === 'ad_events' ? '광고 이벤트' : datum.key === 'ad_budget_states' ? '예산 상태' : datum.key"
    columns = [('원본 저장', 'stored', 0.54, BLUE), ('필수 누락', 'missing', 0.73, AMBER), ('표본 오류', 'invalid', 0.92, RED)]
    marks = heading_marks('광고 원본 로그와 무결성', '컬렉션별 최신 값 · 0건 / 미수신 구분 · 표본 검사')
    for label, field, position, color in columns:
        marks += [{'type': 'text', 'encode': {'update': {'x': {'signal': 'width*'+str(position)},
                    'y': {'value': 83}, 'align': {'value': 'center'}, 'text': {'value': label},
                    'font': {'value': FONT}, 'fontSize': {'value': 10}, 'fill': {'value': MUTED}}}},
                  {'type': 'text', 'from': {'data': 'audit'}, 'encode': {'update': {
                      'x': {'signal': 'width*'+str(position)}, 'y': {'scale': 'rows', 'field': 'key', 'band': 0.5},
                      'align': {'value': 'center'}, 'baseline': {'value': 'middle'}, 'font': {'value': FONT},
                      'fontSize': {'value': 23}, 'fontWeight': {'value': 650},
                      'text': {'signal': "isValid(datum."+field+") ? format(datum."+field+", ',.0f') : '—'"},
                      'fill': {'signal': "!isValid(datum."+field+") ? '"+MUTED+"' : datum."+field+" > 0 ? '"+color+"' : '"+MUTED+"'"},
                      'tooltip': {'signal': "{'컬렉션':datum.key,'지표':'"+label+"','값':datum."+field+'}'}}}}]
    marks += [{'type': 'text', 'from': {'data': 'audit'}, 'encode': {'update': {
                  'x': {'value': 14}, 'y': {'scale': 'rows', 'field': 'key', 'band': 0.5},
                  'baseline': {'value': 'middle'}, 'font': {'value': FONT}, 'fontSize': {'value': 12},
                  'fill': {'value': INK}, 'text': {'field': 'label'}, 'limit': {'signal': 'width*0.4'},
                  'tooltip': {'field': 'key'}}}},
              {'type': 'text', 'encode': {'update': {'x': {'signal': 'width/2'}, 'y': {'signal': 'height/2'},
                  'align': {'value': 'center'}, 'fontSize': {'value': 12}, 'fill': {'value': MUTED},
                  'text': {'value': '광고 로그 점검 상태를 수신하지 못했습니다'},
                  'opacity': {'signal': "length(data('audit')) ? 0 : 1"}}}}]
    return {'$schema': 'https://vega.github.io/schema/vega/v5.json', 'padding': 0,
            'data': [{'name': 'audit', **data, 'transform': [
                {'type': 'formula', 'as': 'label', 'expr': names},
                *[{'type': 'formula', 'as': alias, 'expr': latest_value(field)}
                  for field, alias in [('count', 'stored'), ('pending', 'missing'), ('failed_events', 'invalid')]]]}],
            'scales': [{'name': 'rows', 'type': 'band', 'domain': {'data': 'audit', 'field': 'key'},
                        'range': [98, {'signal': 'height-16'}], 'padding': 0.22}], 'marks': marks}


def definitions():
    panels = []
    def add(key, title, description, spec, x, y, w, h, metric=True):
        panels.append({'key': key, 'title': title, 'description': description, 'spec': spec,
                       'grid': {'x': x, 'y': y, 'w': w, 'h': h}, 'metric': metric})
    add('hero', '서비스 운영 상황', '관측 로그 기반 · 조회 기간과 실시간 상태를 구분합니다.',
        banner('서비스 운영 상황', 'LIVE 카드는 전체 서버 최근 3분 · 분석 그래프는 상단 시간/필터 적용 · 1분 자동 갱신',
               'CAFE MUSIC  /  OPERATIONS CENTER', True), 0, 0, 48, 6, False)
    live = source(query('forwarder', live=True), bucket({'hosts': {'cardinality': {'field': 'host.name'}}}))
    add('live-hosts', '수신 서버', 'LIVE: 전체 서버 최근 3분. 선택 시간/필터와 독립.',
        card('수신 서버 · LIVE', '전체 서버 / 최근 3분', live, "data('metric')[0].hosts.value", ' / 14',
             warning=f"isValid(value) && value < 14 ? '{RED}' : '{TEAL}'"), 0, 6, 8, 8)
    http = [{'bool': {'must_not': [{'match_phrase': {'message': '/health/'}},
                                   {'match_phrase': {'message': '/ops/'}}]}}]
    web_rate = source(query('nginx_access', http), bucket({'server_errors': {'filter': {'range': {'ops.http_status': {'gte': 500}}}}}))
    add('http-error-rate', '앱 HTTP 5xx율', 'Nginx 관측 로그 중 health와 /ops/ 제외. 초기 backfill 중복 이력의 영향을 받을 수 있습니다.',
        card('앱 HTTP 5xx율', 'health · 운영 화면 제외', web_rate,
             "data('metric')[0].doc_count ? 100 * data('metric')[0].server_errors.doc_count / data('metric')[0].doc_count : null",
             ' %', '.2f', RED), 8, 6, 8, 8)
    reco = [{'terms': {'ops.status': ['SUCCEEDED', 'FAILED', 'EXPIRED']}}]
    rec_rate = source(query('recommendation', reco), bucket({'succeeded': {'filter': {'term': {'ops.status': 'SUCCEEDED'}}}}))
    add('recommendation-success', '추천 성공률', '종료 작업 SUCCEEDED/(SUCCEEDED+FAILED+EXPIRED). 요청 생성 시각 기준, 기존 점검 실패 포함.',
        card('추천 성공률', '비시험 카탈로그 / 종료 작업', rec_rate,
             "data('metric')[0].doc_count ? 100 * data('metric')[0].succeeded.doc_count / data('metric')[0].doc_count : null",
             ' %', '.1f', BLUE), 16, 6, 8, 8)
    latency = source(query('recommendation', [{'term': {'ops.status': 'SUCCEEDED'}}]),
                     bucket({'latency': {'percentiles': {'field': 'ops.latency_seconds', 'percents': [95]}}}))
    add('recommendation-p95', '추천 처리 P95', '성공 작업의 생성→결과 저장. 큐 대기 포함이며 HTTP 지연이 아닙니다.',
        card('추천 처리 P95', '큐 대기 + 결과 저장', latency, "data('metric')[0].latency.values['95.0']", ' s', '.2f', BLUE), 24, 6, 8, 8)
    weather_p95 = source(query('pipeline_latency'), bucket({'latency': {'percentiles': {'field': 'ops.pipeline_latency_seconds', 'percents': [95]}}}))
    add('pipeline-p95', '날씨 전달 P95', '수집 요청 시작→해당 request_id의 ES projection 배치 완료.',
        card('날씨 전달 P95', '요청 시작 → ES 발행 완료', weather_p95,
             "data('metric')[0].latency.values['95.0']", ' s', '.1f', TEAL), 32, 6, 8, 8)
    backlog = source(query('forwarder', live=True), {'rows': {'terms': {'field': 'host.name', 'size': 20},
                                   'aggs': {'latest': latest(['ops.queued_events'])}}})
    add('backlog', '로그 전송 대기', 'LIVE: 최근 3분 서버별 최신 gauge만 합산. 반복 snapshot이나 누적 counter를 합산하지 않습니다.',
        card('로그 전송 대기 · LIVE', '최근 수신 서버의 최신 합계', backlog,
             "data('metric')[0].hosts > 0 ? data('metric')[0].pending : null", ' 건', ',.0f', AMBER,
             warning=f"!isValid(value) ? '{MUTED}' : value > 0 ? '{AMBER}' : '{TEAL}'",
             transforms=[{'type': 'formula', 'as': 'pending', 'expr': latest_value('queued_events')},
                         {'type': 'filter', 'expr': 'isValid(datum.pending)'},
                         {'type': 'aggregate', 'fields': ['pending', None], 'ops': ['sum', 'count'],
                          'as': ['pending', 'hosts']}]), 40, 6, 8, 8)
    def section(key, title, description, y):
        add(key, title, description, banner(title, description), 0, y, 48, 4, False)
    section('section-traffic', '01  서비스 트래픽', '관측 HTTP 로그 · health/운영 화면 제외 · 경로의 긴 ID는 묶어서 표시', 14)
    volume = {'rows': {'date_histogram': {'field': '@timestamp', 'fixed_interval': '10m', 'min_doc_count': 1},
                      'aggs': {'status': {'filters': {'keyed': False, 'filters': {
                          '2xx': {'range': {'ops.http_status': {'gte': 200, 'lt': 300}}},
                          '3xx': {'range': {'ops.http_status': {'gte': 300, 'lt': 400}}},
                          '4xx': {'range': {'ops.http_status': {'gte': 400, 'lt': 500}}},
                          '5xx': {'range': {'ops.http_status': {'gte': 500}}}}}}}}}
    add('http-volume', '앱 요청량과 응답 상태', '10분 단위 관측 로그 건수. health 및 /ops/ 제외; 고유 사용자 수가 아닙니다.',
        chart('앱 요청량과 응답 상태', '10분 단위 관측 로그 · health / 운영 화면 제외', source(query('nginx_access', http), volume),
              {'type': 'area', 'opacity': 0.8, 'line': {'strokeWidth': 1}},
              {'x': {'field': 'key', 'type': 'temporal', 'title': None, 'axis': {'labelAngle': 0, 'format': '%H:%M'}},
               'y': {'field': 'status.doc_count', 'type': 'quantitative', 'title': '로그 / 10분', 'stack': 'zero'},
               'color': {'field': 'status.key', 'type': 'nominal', 'scale': {'domain': ['2xx', '3xx', '4xx', '5xx'], 'range': [TEAL, BLUE, AMBER, RED]}},
               'tooltip': [{'field': 'key', 'type': 'temporal', 'title': '시간'}, {'field': 'status.key', 'title': '응답'},
                           {'field': 'status.doc_count', 'title': '관측 건수'}]},
              [{'flatten': ['status.buckets'], 'as': ['status']}]), 0, 18, 28, 15)
    runtime = {'ops_route': {'type': 'keyword', 'script': {'source':
        "def m=params._source.message; if(m==null)return; def p=m.splitOnToken(' '); if(p.length<3)return; "
        "def parts=p[1].splitOnToken('/'); def b=new StringBuilder(); for(def part:parts){if(part.length()==0)continue; "
        "b.append('/'); b.append(part.length()>20 ? ':id' : part);} emit(b.toString());"}}}
    routes = source(query('nginx_access', http, runtime=runtime), {'rows': {'terms': {'field': 'ops_route', 'size': 8}}})
    add('top-routes', '요청이 많은 경로', '정규화된 안전한 접근 메시지에서 추출한 상위 8개 경로. 20자 초과 path segment는 :id로 묶습니다.',
        horizontal('요청이 많은 경로', '상위 8개 경로 · 긴 식별자 묶음', routes,
                   extra_encoding={'y': {'field': 'key', 'type': 'nominal', 'title': None, 'sort': '-x',
                                         'axis': {'labelAngle': 0, 'labelLimit': 235}}}), 28, 18, 20, 15)
    section('section-recommendation', '02  추천 품질과 처리시간', '실제 종료 작업 메타데이터 · 과거 점검 실패 포함 · 요청 생성 시각 기준', 33)
    methods = {'rows': {'terms': {'field': 'ops.method', 'size': 5}, 'aggs': {'status': {'terms': {'field': 'ops.status', 'size': 5}}}}}
    status_transform = [{'flatten': ['status.buckets'], 'as': ['status']},
                        {'calculate': "datum.key === 'RULE_BASED' ? '규칙 추천' : datum.key === 'GEMINI_RECONFIGURE' ? 'Gemini 재설정' : datum.key", 'as': 'method'},
                        {'calculate': "datum.status.key === 'SUCCEEDED' ? '성공' : datum.status.key === 'FAILED' ? '실패' : '만료'", 'as': 'state'}]
    add('recommendation-methods', '추천 방식별 종료 상태', '상태별 종료 작업 건수. 모델 품질 점수/청취 만족도와 다릅니다.',
        horizontal('추천 방식별 종료 상태', '기본 규칙 / Gemini 재설정', source(query('recommendation', reco), methods),
                   status_transform, 'status.doc_count', 'method', extra_encoding={
                       'color': {'field': 'state', 'type': 'nominal', 'scale': STATUS_COLORS},
                       'tooltip': [{'field': 'method', 'title': '방식'}, {'field': 'state', 'title': '상태'}, {'field': 'status.doc_count', 'title': '작업 수'}]}), 0, 37, 16, 14)
    failures = query('recommendation', [{'terms': {'ops.status': ['FAILED', 'EXPIRED']}}])
    add('recommendation-errors', '추천 실패 원인', '실패·만료 작업의 error_type 상위 8개.',
        horizontal('추천 실패 원인', '실패 / 만료 · 상위 8개', source(failures, {'rows': {'terms': {'field': 'ops.error_type', 'size': 8, 'missing': '원인 미기록'}}}),
                   color=RED), 16, 37, 16, 14)
    add('recommendation-latency', '추천 처리시간 추이', '성공 작업 생성→저장, 큐 대기 포함. 10분 cohort P50/P95.',
        percentile_trend('추천 처리시간 추이', '성공 작업 · 10분 구간 P50 / P95', 'recommendation', 'ops.latency_seconds',
                         [{'term': {'ops.status': 'SUCCEEDED'}}]), 32, 37, 16, 14)
    section('section-weather', '03  날씨 데이터 파이프라인', 'API 수신 → 파싱 → Kafka ACK → Spark ES 발행 · 요청/배치 단위를 구분해 해석', 51)
    stages = {'rows': {'filters': {'keyed': False, 'filters': {
        '01 · API 수신': {'term': {'ops.api_received': True}},
        '02 · 파싱 완료': {'term': {'ops.parsed': True}},
        '03 · Kafka ACK': {'term': {'ops.kafka_published': True}}}}}}
    add('weather-stages', '날씨 수집 단계별 통과', 'collection 시도 기준, 같은 요청이 여러 단계에 포함됩니다. 단계 간 수를 합산하지 않습니다.',
        horizontal('날씨 수집 단계별 통과', 'collection 시도 · 단계 간 합산 금지',
                   source(query('weather', [{'term': {'ops.stage': 'collection'}}]), stages),
                   extra_encoding={'y': {'field': 'key', 'type': 'nominal', 'title': None, 'sort': 'ascending', 'axis': {'labelAngle': 0}}}, color=TEAL), 0, 55, 24, 14)
    weather_failures = query('weather', [{'term': {'event.outcome': 'failure'}}])
    causes = {'rows': {'terms': {'field': 'ops.error_type', 'size': 7, 'missing': '원인 미기록'},
                      'aggs': {'category': {'terms': {'field': 'ops.category', 'size': 8, 'missing': 'ES 발행 / 기타'}}}}}
    add('weather-causes', '날씨 실패 원인과 종류', 'collection 및 es_projection 실패. 오류 종류와 원본 category를 함께 표시합니다.',
        horizontal('날씨 실패 원인과 종류', '수집 + ES 발행 · category별 구성', source(weather_failures, causes),
                   [{'flatten': ['category.buckets'], 'as': ['category']}], 'category.doc_count',
                   extra_encoding={'color': {'field': 'category.key', 'type': 'nominal'},
                                   'tooltip': [{'field': 'key', 'title': '원인'}, {'field': 'category.key', 'title': '종류'}, {'field': 'category.doc_count', 'title': '건수'}]}), 24, 55, 24, 14)
    add('weather-collection-latency', '날씨 수집 요청 처리시간', 'HTTP 수신+파싱+Kafka 발행을 포함한 elapsed_seconds이며 API 네트워크 지연만의 측정이 아닙니다.',
        percentile_trend('날씨 수집 요청 처리시간', 'HTTP + 파싱 + Kafka 발행 · P50 / P95', 'weather', 'ops.elapsed_seconds',
                         [{'term': {'ops.stage': 'collection'}}]), 0, 69, 24, 14)
    add('weather-pipeline-latency', '날씨 전달 지연 추이', '같은 request_id의 수집 시작→Spark ES 발행 완료. 개별 행이 아닌 배치 완료 기준.',
        percentile_trend('날씨 전달 지연 추이', '요청 시작 → ES projection 완료 · P50 / P95',
                         'pipeline_latency', 'ops.pipeline_latency_seconds'), 24, 69, 24, 14)
    section('section-operations', '04  서버와 데이터 운영', '오류 로그는 시간 범위 적용 · 서비스 상태는 최근 3분 · 누적 카운터는 최신 값만 사용', 83)
    heat = {'rows': {'terms': {'field': 'host.name', 'size': 20}, 'aggs': {'time': {
        'date_histogram': {'field': '@timestamp', 'fixed_interval': '10m', 'min_doc_count': 1}}}}}
    add('error-heatmap', '서버별 오류 발생 구간', '정규화한 오류 로그 줄 수이며 독립 장애 건수와 다릅니다. stack trace가 여러 줄이면 여러 건으로 관측됩니다.',
        chart('서버별 오류 발생 구간', '오류 로그 줄 수 · 시간대와 서버를 교차 확인',
              source(query(filters=[{'terms': {'log.level': ERRORS}}]), heat), {'type': 'rect', 'cornerRadius': 2},
              {'x': {'field': 'time.key', 'type': 'temporal', 'timeUnit': 'yearmonthdatehoursminutes', 'title': None,
                     'axis': {'labelAngle': 0, 'format': '%H:%M', 'tickCount': 8}},
               'y': {'field': 'key', 'type': 'nominal', 'title': None, 'axis': {'labelAngle': 0, 'grid': False}},
               'color': {'field': 'time.doc_count', 'type': 'quantitative', 'title': '오류 줄 수',
                         'scale': {'range': ['#FFF0E9', '#E65776']}},
               'tooltip': [{'field': 'key', 'title': '서버'}, {'field': 'time.key', 'type': 'temporal', 'title': '구간'}, {'field': 'time.doc_count', 'title': '오류 줄 수'}]},
              [{'flatten': ['time.buckets'], 'as': ['time']}]), 0, 87, 48, 15)
    # Keep the managed visualization ID stable; only replace the metric and its data.
    error_hosts = {'rows': {'terms': {'field': 'host.name', 'size': 10,
                                      'order': {'_count': 'desc'}}}}
    add('service-state', '서버별 오류 TOP 10',
        '선택 기간의 오류 로그 줄 수 상위 10개 서버. 여러 로그 줄이 하나의 장애일 수 있습니다.',
        horizontal('서버별 오류 TOP 10', '선택 기간 · 오류 로그 줄 수 (독립 장애 건수 아님)',
                   source(query(filters=[{'terms': {'log.level': ERRORS}}]), error_hosts),
                   color=RED), 24, 102, 24, 18)
    forwarders = {'rows': {'terms': {'field': 'host.name', 'size': 20},
                          'aggs': {'last': {'max': {'field': '@timestamp'}},
                                   'latest': latest(['ops.queued_events', 'ops.rss_bytes', 'ops.active'])}}}
    add('forwarder-detail', '서버별 수신 상태', '마지막 수신 간격, 전송 대기, Filebeat RSS. 서버 전체 메모리 사용률이 아닙니다.',
        horizontal('서버별 수신 상태', '3분 초과 표시 · hover로 대기 / Filebeat RSS 확인', source(query('forwarder'), forwarders),
                   [{'calculate': '(now()-datum.last.value)/60000', 'as': 'minutes'},
                    {'calculate': latest_value('queued_events'), 'as': 'pending'},
                    {'calculate': '('+latest_value('rss_bytes')+')/1048576', 'as': 'rss_mib'}],
                   'minutes', extra_encoding={
                       'x': {'field': 'minutes', 'type': 'quantitative', 'title': '마지막 수신 후 경과 (분)', 'axis': {'labelAngle': 0}},
                       'color': {'condition': {'test': 'datum.minutes > 3', 'value': RED}, 'value': TEAL},
                       'tooltip': [{'field': 'key', 'title': '서버'}, {'field': 'minutes', 'title': '경과 분', 'format': '.2f'},
                                   {'field': 'pending', 'title': '전송 대기'}, {'field': 'rss_mib', 'title': 'Filebeat RSS MiB', 'format': '.1f'}]}), 0, 102, 24, 18)
    feedback = source(query('feedback'), bucket({'latest': latest(['ops.pending', 'ops.stream_records', 'ops.projected_events'])}))
    add('feedback-state', '피드백 데이터 흐름', '최신 snapshot. 수신 원본과 투영 이벤트는 중복/단위 차이가 있어 차이를 미처리 건수로 단정하지 않습니다.',
        horizontal('피드백 데이터 흐름', '최신 누적 값 · 수신/투영 차이 ≠ 미처리 건수', feedback,
                   [{'calculate': latest_value('pending'), 'as': 'Outbox 대기'},
                    {'calculate': latest_value('stream_records'), 'as': '수신 원본'},
                    {'calculate': latest_value('projected_events'), 'as': '투영 이벤트'},
                    {'fold': ['Outbox 대기', '수신 원본', '투영 이벤트'], 'as': ['metric', 'count']},
                    {'filter': 'isValid(datum.count)'}], 'count', 'metric', color=BLUE), 0, 120, 24, 13)
    ads = source(query('ads_audit'), {'rows': {'terms': {'field': 'ops.collection', 'size': 5},
                                            'aggs': {'latest': latest(['ops.count', 'ops.pending', 'ops.failed_events'])}}})
    add('ads-integrity', '광고 원본 로그와 무결성', '최신 컬렉션별 저장/필수 누락 수와 제한 표본 무결성 오류. 표본 검사를 전수 검사로 해석하지 않습니다.',
        ads_integrity_spec(ads), 24, 120, 24, 13)
    # Compact vertical rhythm: 6 KPI cards remain readable without pushing all charts below the fold.
    positions = {
        'hero': (0, 5), 'live-hosts': (5, 6), 'http-error-rate': (5, 6),
        'recommendation-success': (5, 6), 'recommendation-p95': (5, 6),
        'pipeline-p95': (5, 6), 'backlog': (5, 6), 'section-traffic': (11, 3),
        'http-volume': (14, 14), 'top-routes': (14, 14),
        'section-recommendation': (28, 3), 'recommendation-methods': (31, 13),
        'recommendation-errors': (31, 13), 'recommendation-latency': (31, 13),
        'section-weather': (44, 3), 'weather-stages': (47, 13), 'weather-causes': (47, 13),
        'weather-collection-latency': (60, 13), 'weather-pipeline-latency': (60, 13),
        'section-operations': (73, 3), 'error-heatmap': (76, 13),
        'forwarder-detail': (89, 16), 'service-state': (89, 16),
        'feedback-state': (105, 12), 'ads-integrity': (105, 12)}
    for panel in panels:
        panel['grid']['y'], panel['grid']['h'] = positions[panel['key']]
    assert sum(p['metric'] for p in panels) == 20
    return panels


def saved_objects(dashboard_id=DASHBOARD_ID):
    objects, refs, grid = [], [], []
    for index, panel in enumerate(definitions(), 1):
        identity = PREFIX + panel['key']
        attrs = {'title': panel['title'], 'description': '[managed:music-ops-v2] '+panel['description'],
                 'visState': json.dumps({'title': panel['title'], 'type': 'vega',
                                        'params': {'spec': json.dumps(panel['spec'], ensure_ascii=False)}, 'aggs': []}),
                 'uiStateJSON': '{}', 'kibanaSavedObjectMeta': {'searchSourceJSON': '{}'}}
        objects.append(('visualization', identity, attrs, []))
        name = 'panel_'+str(index)
        refs.append({'type': 'visualization', 'id': identity, 'name': name})
        grid.append({'version': '8.19.23', 'type': 'visualization',
                     'gridData': {**panel['grid'], 'i': str(index)}, 'panelIndex': str(index),
                     'embeddableConfig': {}, 'panelRefName': name})
    attrs = {'title': '카페 음악 서비스 · 운영 관제'+(' (v2 검토본)' if dashboard_id == PREVIEW_ID else ''),
             'description': '20개 로그 기반 지표 · LIVE/기간 조회 구분 · 가로 라벨 · 1분 자동 갱신',
             'panelsJSON': json.dumps(grid), 'optionsJSON': json.dumps({'useMargins': True, 'hidePanelTitles': True}),
             'timeRestore': True, 'timeFrom': 'now-24h', 'timeTo': 'now',
             'refreshInterval': {'pause': False, 'value': 60000},
             'kibanaSavedObjectMeta': {'searchSourceJSON': json.dumps({'query': {'language': 'kuery', 'query': ''}, 'filter': []})}}
    objects.append(('dashboard', dashboard_id, attrs, refs))
    return objects


class Client:
    def __init__(self, config):
        self.base = config['public_url'].rstrip('/')+'/ops'
        self.auth = 'Basic '+base64.b64encode(('ops_admin:'+config['viewer_password']).encode()).decode()

    def request(self, method, path, body=None):
        req = urllib.request.Request(self.base+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': self.auth, 'Content-Type': 'application/json', 'kbn-xsrf': 'dashboard-redesign'}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode()
            raise RuntimeError('kibana_api_'+str(error.code)+':'+detail[:1500]) from None

    def get(self, kind, identity):
        try:
            return self.request('GET', '/api/saved_objects/'+kind+'/'+identity)
        except RuntimeError as error:
            if str(error).startswith('kibana_api_404:'):
                return None
            raise

    def es(self, body):
        return self.request('POST', '/api/console/proxy?'+urllib.parse.urlencode({'path': 'ops-mlo-*/_search', 'method': 'POST'}), body)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def publish(client, state_dir, preview=True):
    """Own-object version ledger plus CAS on the existing dashboard prevent lost edits."""
    state_dir = Path(state_dir)
    ledger_path = state_dir/'v2-published-ledger.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    def save():
        temporary = ledger_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2))
        temporary.chmod(0o600)
        temporary.replace(ledger_path)
    target = PREVIEW_ID if preview else DASHBOARD_ID
    if not preview:
        original = json.loads((state_dir/'dashboard-before.json').read_text())
        current = client.get('dashboard', target)
        expected = ledger.get('dashboard/'+target, {}).get('version', original['version'])
        if current['version'] != expected:
            raise RuntimeError('existing_dashboard_changed_by_another_editor; re-review required')
    for kind, identity, attrs, refs in saved_objects(target):
        key = kind+'/'+identity
        desired = {'attributes': attrs, 'references': refs}
        current = client.get(kind, identity)
        if current:
            owned = ledger.get(key)
            if kind == 'dashboard' and identity == DASHBOARD_ID:
                expected = ledger.get(key, {}).get('version', original['version'])
            elif owned:
                expected = owned['version']
            else:
                raise RuntimeError('v2_object_exists_without_ownership_receipt:'+key)
            if current['version'] != expected:
                raise RuntimeError('object_changed_by_another_editor:'+key)
            if owned and owned.get('digest') == digest(desired):
                continue
            result = client.request('PUT', '/api/saved_objects/'+key, {**desired, 'version': expected})
        else:
            result = client.request('POST', '/api/saved_objects/'+key, desired)
        ledger[key] = {'version': result['version'], 'digest': digest(desired)}
        save()
    return {'dashboard_id': target, 'metrics': 20, 'visualizations': len(definitions()), 'concurrency_check': True}
