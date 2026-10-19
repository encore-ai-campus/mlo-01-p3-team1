"""Isolated Kibana saved objects for anonymous guest behavior analytics.

Reuse the approved v2 visual language, never update music-operations-v1.
Install with a Kibana admin credential after a preview and ownership review.
"""
import json
from pathlib import Path
import hashlib
import urllib.request
import base64

from dashboard_v2 import banner, card, chart, horizontal, BLUE, TEAL, AMBER, RED

DASHBOARD_ID = "music-guest-behavior-v1"
PREFIX = "music-guest-v1-"
EVENT_INDEX = "analytics-mlo-guest-events-*"
STATE_INDEX = "analytics-mlo-guest-summary-v1"
BLUEPRINT = "CAFE MUSIC / GUEST BEHAVIOR CENTER"


def query(index, filters=(), current=False):
    extra = list(filters)
    if current:
        extra.append({"term": {"_id": "current"}})
        return {"size": 0, "query": {"bool": {"filter": extra}}}
    return {"size": 0, "query": {"bool": {
        "must": ["%dashboard_context-must_clause%"],
        "must_not": ["%dashboard_context-must_not_clause%"],
        "filter": ["%dashboard_context-filter_clause%",
                   {"range": {"@timestamp": {"%timefilter%": True}}}, *extra]}}}


def source(index, aggs, filters=(), prop="aggregations.rows.buckets", current=False):
    return {"url": {"index": index, "body": {**query(index, filters, current),
                                               "aggs": aggs}}, "format": {"property": prop}}


def event_filter(*actions):
    return [{"terms": {"action": list(actions)}}] if actions else []


def total(name, filters=()):
    return source(EVENT_INDEX, {"rows": {"filters": {"filters": [{"match_all": {}}]}}}, filters,
                  "aggregations.rows.buckets")


def current(field):
    aggs = {"rows": {"filters": {"filters": [{"match_all": {}}]},
                      "aggs": {"value": {"max": {"field": field}}}}}
    return source(STATE_INDEX, aggs, current=True)


def basic_chart(title, subtitle, spec, color=BLUE):
    return horizontal(title, subtitle, spec, color=color)


def time_chart(title, subtitle, filters=(), interval="1h", breakdown=False):
    agg = {"rows": {"date_histogram": {"field": "@timestamp", "fixed_interval": interval,
                                       "min_doc_count": 1}}}
    transforms = []
    if breakdown:
        agg["rows"]["aggs"] = {"actions": {"terms": {"field": "action", "size": 8}}}
        transforms = [{"flatten": ["actions.buckets"], "as": ["action"]}]
        value = "action.doc_count"
        color = {"field": "action.key", "type": "nominal",
                 "scale": {"domain": ["LIKE", "DISLIKE", "EXCLUDED", "EXCLUSION_CANCELLED", "RATING_CHANGED"],
                           "range": [TEAL, RED, AMBER, BLUE, "#8A78D0"]}}
        tooltip = [{"field": "action.key", "title": "행동"}]
    else:
        value = "doc_count"
        color = {"value": BLUE}
        tooltip = []
    return chart(title, subtitle, source(EVENT_INDEX, agg, filters),
                 {"type": "line", "point": True, "strokeWidth": 2.3},
                 {"x": {"field": "key", "type": "temporal", "title": None},
                  "y": {"field": value, "type": "quantitative", "title": None},
                  "color": color,
                  "tooltip": [{"field": "key", "type": "temporal", "title": "시간"}, *tooltip,
                              {"field": value, "type": "quantitative", "title": "건수"}]}, transforms)


def group_chart(title, subtitle, field, filters=(), size=10, color=BLUE):
    terms = {"field": field, "size": size}
    if field not in {"hour_kst", "weekday_kst"}:
        terms["missing"] = "미확인"
    else:
        terms["order"] = {"_key": "asc"}
    agg = {"rows": {"terms": terms}}
    return horizontal(title, subtitle, source(EVENT_INDEX, agg, filters), color=color)


def rating_chart():
    agg = {"rows": {"terms": {"field": "rating_value", "size": 5, "order": {"_key": "asc"}}}}
    return chart("선곡표 별점 분포", "평점 변경 이벤트 기준 · 동일 선곡표의 재평가가 포함됩니다",
                 source(EVENT_INDEX, agg, event_filter("RATING_CHANGED")),
                 {"type": "bar", "cornerRadiusEnd": 5, "color": BLUE},
                 {"x": {"field": "key", "type": "ordinal", "title": "별점 (1~5)"},
                  "y": {"field": "doc_count", "type": "quantitative", "title": None},
                  "tooltip": [{"field": "key", "title": "별점"},
                              {"field": "doc_count", "title": "건수"}]})


def methods_chart():
    aggs = {"rows": {"terms": {"field": "method", "size": 5},
                     "aggs": {"actions": {"terms": {"field": "action", "size": 8}}}}}
    return chart("추천 방식별 반응", "기본 규칙 / Gemini 재구성 · 좋아요·싫어요 이벤트",
                 source(EVENT_INDEX, aggs, event_filter("LIKE", "DISLIKE")),
                 {"type": "bar", "cornerRadiusEnd": 3},
                 {"x": {"field": "key", "type": "nominal", "title": None, "axis": {"labelAngle": 0}},
                  "y": {"field": "action.doc_count", "type": "quantitative", "title": None},
                  "color": {"field": "action.key", "type": "nominal",
                            "scale": {"domain": ["LIKE", "DISLIKE"], "range": [TEAL, RED]}},
                  "tooltip": [{"field": "key", "title": "추천 방식"},
                              {"field": "action.key", "title": "반응"},
                              {"field": "action.doc_count", "title": "건수"}]},
                 [{"flatten": ["actions.buckets"], "as": ["action"]}])


def definitions():
    rows = []
    def add(key, title, desc, spec, x, y, w, h):
        rows.append({"key": key, "title": title, "description": desc, "spec": spec,
                     "grid": {"x": x, "y": y, "w": w, "h": h}})
    add("hero", "비회원 행동 분석", "기간 이벤트 분석과 전체 현재 상태 구분",
        banner("비회원 행동 분석",
               "로그인 기반 사용자가 아닌 익명 피드백 · 상단 시간 필터는 이벤트에 적용 · 현재 상태는 전체 기준",
               BLUEPRINT, True), 0, 0, 48, 6)
    # Current-state snapshot is an overwrite-by-ID document, not time-series data.
    for idx, (key, title, field, unit, fmt, color) in enumerate([
        ("like", "현재 좋아요", "current_like", " 건", ",.0f", TEAL),
        ("dislike", "현재 싫어요", "current_dislike", " 건", ",.0f", RED),
        ("positive", "현재 긍정 반응률", "current_positive_pct", " %", ".1f", TEAL),
        ("rating", "현재 평균 별점", "current_rating_mean", " / 5", ".2f", BLUE),
        ("excluded", "현재 제외곡", "current_excluded", " 곡", ",.0f", AMBER),
        ("playlists", "평가 참여 선곡표", "participating_playlists", " 개", ",.0f", BLUE),
    ]):
        add(key, title, "현재 반응 상태, 시간 필터에 독립",
            card(title, "전체 현행 상태 / 비시험", current(field),
                 "data('metric')[0].value.value", unit, fmt, color),
            8 * idx, 6, 8, 8)
    def section(key, title, desc, y):
        add(key, title, desc, banner(title, desc), 0, y, 48, 4)
    section("activity", "01  익명 행동 흐름", "이벤트 발생 시각 / 필터 적용 · 상태 변경은 중복 가능", 14)
    add("trend", "시간대별 행동 추이", "좋아요·싫어요·제외·별점", time_chart(
        "행동 발생 추이", "1시간 간격 · 이벤트 건수", breakdown=True), 0, 18, 30, 15)
    add("action-types", "행동 종류", "행동 이벤트별 분포", group_chart(
        "행동별 이벤트 비중", "좋아요/싫어요/제외/해제/평점", "action", color=TEAL), 30, 18, 18, 15)
    add("hour", "한국 시간대", "한국 시각 기준", group_chart(
        "행동이 발생한 시간대", "한국 시간 0~23시 · 활동 사용자 수가 아님", "hour_kst", size=24), 0, 33, 24, 14)
    add("weekday", "요일별 행동", "월요일=0", group_chart(
        "요일별 행동 건수", "KST · 0 월요일, 6 일요일", "weekday_kst", size=7, color=AMBER), 24, 33, 24, 14)
    section("quality", "02  좋아요와 싫어요", "곡별 피드백 · 반응 전환 / 해제를 구분", 47)
    add("positive-tracks", "좋아요가 많은 곡", "이벤트 기준 중복 가능", group_chart(
        "좋아요 상위 곡", "곡 이름 기준 합산 · 서로 다른 동명곡이 합쳐질 수 있습니다",
        "track_title", event_filter("LIKE"), color=TEAL), 0, 51, 24, 15)
    add("negative-tracks", "싫어요가 많은 곡", "이벤트 기준 중복 가능", group_chart(
        "싫어요 상위 곡", "동명곡 구분은 track_key 기준 상세 조회 필요",
        "track_title", event_filter("DISLIKE"), color=RED), 24, 51, 24, 15)
    add("transitions", "피드백 전환", "LIKE→DISLIKE 등 상태 변경", group_chart(
        "좋아요/싫어요 상태 전환", "기존 반응 → 신규 반응, 취소 포함",
        "transition", color=AMBER), 0, 66, 24, 14)
    add("genres", "장르별 반응", "곡 장르 중복 태깅 가능", group_chart(
        "좋아요가 발생한 장르", "한 곡이 여러 장르에 포함될 수 있습니다",
        "genre", event_filter("LIKE"), color=TEAL), 24, 66, 24, 14)
    section("section-rating", "03  선곡표 만족도", "선곡표 단위 1~5점 · 곡별 별점 아님", 80)
    add("rating-dist", "별점 분포", "평점 변경 이벤트", rating_chart(), 0, 84, 24, 15)
    add("rating-methods", "추천 방식별 반응", "추천 성공과 만족도 차이", methods_chart(), 24, 84, 24, 15)
    add("weather", "날씨 사용 유무", "날씨 모드별 평가 행동", group_chart(
        "날씨 반영 여부별 반응", "해당 행동 발생 당시 선택 조건", "weather_mode",
        event_filter("LIKE", "DISLIKE"), color=BLUE), 0, 99, 24, 14)
    add("themes", "선택 테마", "당시 곡 테마", group_chart(
        "선호 반응이 발생한 곡 테마", "곡 태그 다중 값 · 합계는 이벤트 총수와 다를 수 있음",
        "theme", event_filter("LIKE"), color=TEAL), 24, 99, 24, 14)
    section("exclusion", "04  제외곡과 데이터 수집", "비회원 제외 / 제외 취소 · 데이터 처리 맥락", 113)
    add("exclusions", "제외된 곡", "제외 이벤트 상위 곡", group_chart(
        "제외 요청 상위 곡", "실제 제외 유지 수가 아닌 제외 발생 이력", "track_title",
        event_filter("EXCLUDED"), color=AMBER), 0, 117, 24, 15)
    add("exclusion-trend", "제외 및 복원", "시간별 제외/해제", time_chart(
        "제외 행동의 시간별 변화", "제외·제외 취소 이벤트 건수",
        event_filter("EXCLUDED", "EXCLUSION_CANCELLED"), breakdown=True),
        24, 117, 24, 15)
    add("pending", "피드백 전송 대기", "PostgreSQL outbox 현재 상태", card(
        "Outbox 전송 대기", "데이터 처리 상태 · 현재 값", current("outbox_pending"),
        "data('metric')[0].value.value", " 건", ",.0f", AMBER), 0, 132, 24, 9)
    add("projected", "투영 이벤트", "PostgreSQL projection 현재 값", card(
        "반영된 피드백 이벤트", "누적 투영 건수 · 현재 값", current("projected_events"),
        "data('metric')[0].value.value", " 건", ",.0f", BLUE), 24, 132, 24, 9)
    return rows


def objects():
    visualizations, refs, layout = [], [], []
    for n, panel in enumerate(definitions(), 1):
        key = PREFIX + panel["key"]
        visualizations.append(("visualization", key, {
            "title": panel["title"],
            "description": "[managed:music-guest-v1] " + panel["description"],
            "visState": json.dumps({"title": panel["title"], "type": "vega",
                                    "params": {"spec": json.dumps(panel["spec"], ensure_ascii=False)},
                                    "aggs": []}, ensure_ascii=False),
            "uiStateJSON": "{}", "kibanaSavedObjectMeta": {"searchSourceJSON": "{}"}}, []))
        refname = "panel_" + str(n)
        refs.append({"type": "visualization", "id": key, "name": refname})
        layout.append({"version": "8.19.23", "type": "visualization",
                       "gridData": {**panel["grid"], "i": str(n)},
                       "panelIndex": str(n), "embeddableConfig": {},
                       "panelRefName": refname})
    dashboard = ("dashboard", DASHBOARD_ID, {
        "title": "카페 음악 서비스 · 비회원 행동 분석",
        "description": "PostgreSQL 비회원 반응/별점/제외 · 이벤트는 기간 기준 · 상태 카드는 현재 전체 기준",
        "panelsJSON": json.dumps(layout),
        "optionsJSON": json.dumps({"useMargins": True, "hidePanelTitles": True}),
        "timeRestore": True, "timeFrom": "now-7d", "timeTo": "now",
        "refreshInterval": {"pause": False, "value": 60000},
        "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({
            "query": {"language": "kuery", "query": ""}, "filter": []})}}, refs)
    return [*visualizations, dashboard]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def publish(client, state_dir, dry_run=True):
    """Fail closed on unexpected objects or another editor's changes."""
    items = objects()
    if dry_run:
        return {"dashboard_id": DASHBOARD_ID, "panels": len(items)-1,
                "planned_objects": len(items), "dry_run": True}
    state = Path(state_dir)
    ledger_path = state / "guest-v1-published-ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    state.mkdir(parents=True, exist_ok=True)
    # Check every identity before the first write, avoiding partial collision updates.
    for kind, key, _, _ in items:
        old = client.get(kind, key)
        owned = ledger.get(kind + "/" + key)
        if old and (not owned or old["version"] != owned["version"]):
            raise RuntimeError("guest_dashboard_object_not_owned_or_changed:" + kind + "/" + key)
    for kind, key, attributes, references in items:
        identity = kind + "/" + key
        desired = {"attributes": attributes, "references": references}
        old = client.get(kind, key)
        if old:
            owned = ledger.get(identity)
            if not owned or old["version"] != owned["version"]:
                raise RuntimeError("guest_dashboard_object_not_owned_or_changed:" + identity)
            if owned["digest"] == digest(desired):
                continue
            result = client.request("PUT", "/api/saved_objects/" + identity,
                                    {**desired, "version": old["version"]})
        else:
            result = client.request("POST", "/api/saved_objects/" + identity, desired)
        ledger[identity] = {"version": result["version"], "digest": digest(desired)}
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2))
        ledger_path.chmod(0o600)
    return {"dashboard_id": DASHBOARD_ID, "panels": len(items)-1,
            "dry_run": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-json", action="store_true")
    options = parser.parse_args()
    print(json.dumps({"dashboard": DASHBOARD_ID, "panels": len(definitions()),
                      "objects": objects() if options.preview_json else None}, ensure_ascii=False))
