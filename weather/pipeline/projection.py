"""격자 한 개의 최신 기본 자료와 같은 대상 시각의 보완값 구성."""
from datetime import datetime
from weather.pipeline.common import OBS, FORECAST


def fields(rows, categories):
    by_category = {r['category']: r for r in rows}
    values = {}
    for category in categories:
        row = by_category.get(category)
        if row:
            values[category] = dict(row['measurement'], source=row['source'],
                                    issued_at=row['issued_at'], target_at=row['target_at'],
                                    received_at=row['received_at'], history_id=row.get('history_id',row['_id']))
            for key in ('mapping_version','source_hash','rule_version','data_mode','spatial_basis','source_ix','source_iy','source_lat','source_lon','spatial_distance_km'):
                if key in row:
                    values[category][key] = row[key]
    missing = [c for c in categories if c not in values or values[c]['status'] != 'valid']
    return {'values': values, 'missing': missing, 'complete': not missing}


def project_grid(rows):
    """한 격자의 정제 행 목록 → observation, forecast, sky_context를 가진 dict.

    observation에는 완성된 실황 한 회차, forecast에는 선택한 예보 회차의 대상별 값.
    rows는 merge_rows로 중복·최신 회차를 정리한 비어 있지 않은 목록.
    """
    nx, ny = rows[0]['nx'], rows[0]['ny']
    obs = [r for r in rows if r['source'] == 'odam']
    fc = [r for r in rows if r['source'] == 'vsrt']
    doc = dict(nx=nx, ny=ny, observation=None, forecast=[], supplements_pending=True)
    if obs:
        # 항목별 과거 값 섞기 대신, 8항목이 모두 도착한 한 회차 선택.
        targets = sorted({r['target_at'] for r in obs}, reverse=True)
        ready = [t for t in targets if set(OBS) <= {r['category'] for r in obs if r['target_at'] == t}]
        if ready:
            target = ready[0]
            doc['observation'] = dict(target_at=target, **fields([r for r in obs if r['target_at'] == target], OBS))
            if target != targets[0]:
                pending = fields([r for r in obs if r['target_at'] == targets[0]], OBS)
                doc['observation'].update(pending_target_at=targets[0], pending_missing=pending['missing'])
    if fc:
        issues = sorted({r['issued_at'] for r in fc}, reverse=True)
        ready = []
        for issue in issues:
            candidate = [r for r in fc if r['issued_at'] == issue]
            targets = {r['target_at'] for r in candidate}
            if len(targets) == 6 and all(set(FORECAST) <= {r['category'] for r in candidate if r['target_at'] == t} for t in targets):
                ready.append(issue)
        # 첫 수집에서 완성 회차가 없으면 부분 자료와 품질을 제공.
        issued = ready[0] if ready else issues[0]
        fc = [r for r in fc if r['issued_at'] == issued]
        for target in sorted({r['target_at'] for r in fc}):
            hour = dict(target_at=target, issued_at=issued,
                        **fields([r for r in fc if r['target_at'] == target], FORECAST))
            supplements = [r for r in rows if r['source'] in ('KIMG','shrt') and r['target_at'] == target]
            expected = ['SNO', 'TCDC']
            hour['supplements'] = fields(supplements, expected)
            hour['supplements']['TCDC_applicable'] = 'TCDC' in expected
            doc['forecast'].append(hour)
        doc['supplements_pending'] = any(not h['supplements']['complete'] for h in doc['forecast'])
    # 이전 예보의 현재 시간 SKY를 유지하고, 같은 시각 KIM과 조회 시 결합.
    context = [r for r in rows if (r['source']=='vsrt' and r['category']=='SKY')
               or (r['source']=='KIMG' and r['category']=='TCDC')]
    doc['sky_context'] = []
    for target in sorted({r['target_at'] for r in context}):
        selected = {}
        for row in context:
            if row['target_at'] != target: continue
            code = row['category']
            if code not in selected or (row['issued_at'],row['received_at']) > (selected[code]['issued_at'],selected[code]['received_at']):
                selected[code] = row
        doc['sky_context'].append(dict(target_at=target,
            values=fields([selected['SKY']] if 'SKY' in selected else [],['SKY'])['values'],
            supplements=fields([selected['TCDC']] if 'TCDC' in selected else [],['TCDC'])))
    doc['base_complete'] = bool(doc['observation'] and doc['observation']['complete'] and
                                len(doc['forecast']) == 6 and all(h['complete'] for h in doc['forecast']))
    return doc
