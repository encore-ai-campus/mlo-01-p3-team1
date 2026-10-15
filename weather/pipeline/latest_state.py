"""저장소와 독립적인 격자별 최신 회차 병합. 원천·장기 이력 미저장."""
from weather.pipeline.common import OBS, FORECAST

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
