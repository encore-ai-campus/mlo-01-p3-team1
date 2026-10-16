"""격자별 최신 회차 병합. DB 접속 없이 정제 행 목록만 선택."""
from pipeline.weather.common import OBS, FORECAST


def newer(candidate, previous):
    """같은 항목의 두 행 중 candidate를 채택해야 하면 True."""
    same_original = (candidate['issued_at'], candidate['source_hash']) == (
        previous['issued_at'], previous['source_hash']
    )
    if same_original:
        candidate_rule = int(candidate['rule_version'].removeprefix('normalize_v'))
        previous_rule = int(previous['rule_version'].removeprefix('normalize_v'))
        if candidate_rule != previous_rule:
            return candidate_rule > previous_rule
    candidate_order = (candidate['issued_at'], candidate['received_at'], candidate['source_hash'])
    previous_order = (previous['issued_at'], previous['received_at'], previous['source_hash'])
    return candidate_order > previous_order


def select_base_rounds(rows, source, categories):
    """최신 도착 회차와 가장 최근에 모든 항목이 도착한 회차를 유지."""
    if not rows:
        return []
    time_field = 'target_at' if source == 'odam' else 'issued_at'
    round_times = sorted({row[time_field] for row in rows}, reverse=True)
    complete_rounds = []
    for round_time in round_times:
        round_rows = [row for row in rows if row[time_field] == round_time]
        target_times = {row['target_at'] for row in round_rows}
        all_items_arrived = True
        for target_time in target_times:
            arrived_categories = {
                row['category'] for row in round_rows if row['target_at'] == target_time
            }
            if not set(categories).issubset(arrived_categories):
                all_items_arrived = False
                break
        enough_targets = source == 'odam' or len(target_times) == 6
        if all_items_arrived and enough_targets:
            complete_rounds.append(round_time)

    # 최신 회차가 일부만 도착했으면 기존 완성 회차도 남겨 둠.
    keep_times = {round_times[0]}
    if complete_rounds:
        keep_times.add(complete_rounds[0])
    return [row for row in rows if row[time_field] in keep_times]


def latest_per_target(rows, target_limit):
    """최근 대상 시각만 남기고, 같은 대상 시각·항목은 최신 발표 행 하나 선택."""
    target_times = sorted({row['target_at'] for row in rows}, reverse=True)[:target_limit]
    latest = {}
    for row in rows:
        if row['target_at'] not in target_times:
            continue
        key = (row['target_at'], row['category'])
        previous = latest.get(key)
        if previous is None or newer(row, previous):
            latest[key] = row
    return list(latest.values())


def trim_rows(rows):
    keep = []
    for source, categories in [('odam', OBS), ('vsrt', FORECAST)]:
        source_rows = [row for row in rows if row['source'] == source]
        keep.extend(select_base_rounds(source_rows, source, categories))

    # 예보 회차가 바뀌어도 현재 시각의 SKY를 조회할 수 있도록 최근 8개 대상 유지.
    sky_rows = [row for row in rows if row['source'] == 'vsrt' and row['category'] == 'SKY']
    kept_ids = {row['_id'] for row in keep}
    for row in latest_per_target(sky_rows, 8):
        if row['_id'] not in kept_ids:
            keep.append(row)

    # SNO와 KIM은 각각 최근 12개 대상 시각의 보완값 유지.
    for source in ('shrt', 'KIMG'):
        source_rows = [row for row in rows if row['source'] == source]
        keep.extend(latest_per_target(source_rows, 12))
    return keep


def merge_rows(previous, incoming):
    """저장된 행 + 새로 받은 행 → 중복을 제거하고 보관 범위를 제한한 행 목록.

    비교 기준: source, issued_at, target_at, category. 값이 결측인 행도 유지.
    """
    by_key = {}
    for row in previous + incoming:
        key = (row['source'], row['issued_at'], row['target_at'], row['category'])
        saved = by_key.get(key)
        if saved is None or newer(row, saved):
            by_key[key] = row
    return trim_rows(list(by_key.values()))
