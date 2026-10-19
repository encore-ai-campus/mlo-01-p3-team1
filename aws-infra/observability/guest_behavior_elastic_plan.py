"""Elasticsearch analytics index setup plan. Does not execute network requests."""
import json
from pathlib import Path

EVENT_PROPERTIES = {
    "@timestamp": {"type": "date"},
    **{k: {"type": "keyword", "ignore_above": 256} for k in [
        "event_key", "event_type", "action", "method", "playlist_key",
        "track_key", "track_title", "track_artist", "weather_mode",
        "weather_code", "transition", "genre", "theme",
        "selected_genre", "selected_theme"]},
    **{k: {"type": "integer"} for k in [
        "hour_kst", "weekday_kst", "rating_value", "rating_previous"]},
    "is_test": {"type": "boolean"},
}
STATE_PROPERTIES = {
    "@timestamp": {"type": "date"}, "source": {"type": "keyword"},
    "is_test": {"type": "boolean"},
    **{k: {"type": "long"} for k in [
        "current_like", "current_dislike", "current_rating_count",
        "current_excluded", "participating_playlists",
        "outbox_pending", "projected_events"]},
    "current_positive_pct": {"type": "double"},
    "current_rating_mean": {"type": "double"},
    **{k: {"type": "object", "enabled": False} for k in [
        "rating_distribution", "top_positive", "top_negative",
        "by_method", "by_genre"]},
}

def template(pattern, properties):
    return {
        "index_patterns": [pattern], "priority": 250,
        "template": {
            "settings": {"number_of_shards": 1, "number_of_replicas": 1,
                         "refresh_interval": "5s"},
            "mappings": {"dynamic": "strict", "properties": properties}
        },
    }

def plans():
    names = ["analytics-mlo-guest-events-*", "analytics-mlo-guest-summary-*"]
    return [
        {"method": "PUT", "path": "/_index_template/analytics-mlo-guest-events-v1",
         "body": template(names[0], EVENT_PROPERTIES)},
        {"method": "PUT", "path": "/_index_template/analytics-mlo-guest-summary-v1",
         "body": template(names[1], STATE_PROPERTIES)},
        {"method": "PUT", "path": "/_security/role/analytics_mlo_guest_writer",
         "body": {"cluster": ["monitor"], "indices": [
             {"names": names, "privileges": [
                 "create_index", "create_doc", "index", "view_index_metadata"]}]}},
        {"method": "PUT", "path": "/_security/role/analytics_mlo_guest_viewer",
         "body": {"cluster": [], "indices": [
             {"names": names, "privileges": ["read", "view_index_metadata"]}]}},
    ]

if __name__ == "__main__":
    print(json.dumps({"deploy": False, "operations": plans()}, ensure_ascii=False, indent=2))
