"""Privacy-minimized, read-only PostgreSQL guest feedback -> Elasticsearch.

Requires the deployed Django application's environment and a dedicated ES writer.
Never exports owner/guest/family IDs, cookies, full payloads, or snapshots.
Run under a systemd timer on one designated Control host only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import tempfile
import urllib.error
import urllib.request

EVENTS_PATTERN = "analytics-mlo-guest-events-*"
SUMMARY_INDEX = "analytics-mlo-guest-summary-v1"
ACTIONS = {
    "TRACK_REACTION_CHANGED": "REACTION_CHANGED",
    "TRACK_REACTION_CLEARED": "REACTION_CLEARED",
    "PLAYLIST_RATING_CHANGED": "RATING_CHANGED",
    "PLAYLIST_RATING_CLEARED": "RATING_CLEARED",
    "TRACK_EXCLUDED": "EXCLUDED",
    "TRACK_EXCLUSION_CANCELLED": "EXCLUSION_CANCELLED",
    "PLAYLIST_APPROVED": "APPROVED",
}
KST = timezone(timedelta(hours=9))
MAX_STATES = 100000
MAX_BATCHES = 20


def safe_text(value, limit=86):
    if isinstance(value, (tuple, list)):
        value = ", ".join(str(item) for item in value[:2])
    if not isinstance(value, str):
        return "미확인"
    value = re.sub(r"[\x00-\x1f\x7f<>]", " ", value)
    return re.sub(r"\s+", " ", value).strip()[:limit] or "미확인"


def tags(value):
    return sorted({safe_text(v, 32) for v in value[:12] if isinstance(v, str) and v.strip()})[:12] if isinstance(value, list) else []


def digest_id(namespace, value):
    return hashlib.sha256((namespace + ":" + str(value)).encode()).hexdigest()[:24]


def normalize_event(row, method="UNKNOWN"):
    payload = row.get("payload") or {}
    kind = row["event_type"]
    if kind not in ACTIONS:
        return None
    ts = row["occurred_at"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert ts.tzinfo is not None
    local = ts.astimezone(KST)
    context = payload.get("context_snapshot") or {}
    options = context.get("options") or {}
    track = payload.get("track_snapshot") or {}
    previous = payload.get("previous_value")
    current = payload.get("new_value")
    action = ACTIONS[kind]
    if kind == "TRACK_REACTION_CHANGED":
        if current not in ("LIKE", "DISLIKE"):
            return None
        action = current
    if kind == "PLAYLIST_RATING_CHANGED" and (type(current) is not int or not 1 <= current <= 5):
        return None
    transition = None
    if kind.startswith("TRACK_REACTION"):
        src = previous if previous in ("LIKE", "DISLIKE") else "NONE"
        dest = current if current in ("LIKE", "DISLIKE") else "NONE"
        transition = src + "_TO_" + dest
    raw_track = row.get("track_id") or payload.get("track_id")
    out = {
        "@timestamp": ts.isoformat(),
        "event_key": digest_id("feedback-event", row["event_id"]),
        "event_type": kind, "action": action, "method": method if method in ("RULE_BASED", "GEMINI_RECONFIGURE") else "UNKNOWN",
        "playlist_key": digest_id("playlist", row["source_playlist_id"]) if row.get("source_playlist_id") else None,
        "track_key": digest_id("catalog-track", raw_track) if raw_track else None,
        "track_title": safe_text(track.get("track_name")) if raw_track else None,
        "track_artist": safe_text(track.get("artists_name")) if raw_track else None,
        "genre": tags(track.get("genre_group_codes")),
        "theme": tags(track.get("theme_codes")),
        "selected_genre": tags(options.get("selected_genre_codes")),
        "selected_theme": tags(options.get("selected_theme_codes")),
        "weather_mode": options.get("weather_influence_mode") if options.get("weather_influence_mode") in ("ON", "OFF") else "UNKNOWN",
        "weather_code": safe_text(context.get("weather_code"), 32) if context.get("weather_code") else None,
        "hour_kst": local.hour, "weekday_kst": local.weekday(),
        "rating_value": current if kind == "PLAYLIST_RATING_CHANGED" else None,
        "rating_previous": previous if type(previous) is int and 1 <= previous <= 5 else None,
        "transition": transition, "is_test": False,
    }
    # Do not copy the input row or its full JSON snapshots into the output.
    return {k: v for k, v in out.items() if v is not None}


def normalize_current_state(rows, metadata, excluded_count=0, outbox_pending=0,
                            projected_events=0, as_of=None):
    """Aggregate only current explicit responses; no inferred users or listening."""
    counts = Counter()
    ratings = Counter()
    methods = defaultdict(Counter)
    genres = defaultdict(Counter)
    tracks = defaultdict(Counter)
    track_labels = {}
    playlists = set()
    for row in rows:
        event = metadata.get(row.get("last_event_id"))
        if not event or event.get("is_test") is True:
            continue
        kind, value = row["target_kind"], row["value"]
        if kind == "TRACK" and value not in ("LIKE", "DISLIKE"):
            continue
        if kind == "PLAYLIST" and (type(value) is not int or value not in range(1, 6)):
            continue
        playlists.add(row["playlist_id"])
        method = row.get("playlist__job__method") or "UNKNOWN"
        if kind == "TRACK":
            counts[value] += 1
            methods[method][value] += 1
            track_id = row["track_id"]
            tracks[track_id][value] += 1
            snap = (event.get("payload") or {}).get("track_snapshot") or {}
            track_labels[track_id] = (safe_text(snap.get("track_name")),
                                      safe_text(snap.get("artists_name")))
            for genre in tags(snap.get("genre_group_codes")):
                genres[genre][value] += 1
        else:
            ratings[value] += 1
            methods[method]["rating_count"] += 1
            methods[method]["rating_sum"] += value

    like, dislike = counts["LIKE"], counts["DISLIKE"]
    rated = sum(ratings.values())
    def ranking(field):
        items = []
        for track_id, amounts in tracks.items():
            if amounts[field] <= 0:
                continue
            name, artist = track_labels.get(track_id, ("미확인", "미확인"))
            items.append({"track": name, "artist": artist,
                          "track_key": digest_id("catalog-track", track_id),
                          "likes": amounts["LIKE"], "dislikes": amounts["DISLIKE"],
                          "evaluations": amounts["LIKE"] + amounts["DISLIKE"]})
        return sorted(items, key=lambda t: (-t["likes" if field == "LIKE" else "dislikes"],
                                            -t["evaluations"], t["track_key"]))[:12]

    method_rows = [{"method": method, "likes": count["LIKE"], "dislikes": count["DISLIKE"],
                    "rating_count": count["rating_count"],
                    "rating_mean": round(count["rating_sum"] / count["rating_count"], 2) if count["rating_count"] else None}
                   for method, count in sorted(methods.items())]
    genre_rows = [{"genre": genre, "likes": amounts["LIKE"], "dislikes": amounts["DISLIKE"]}
                  for genre, amounts in sorted(genres.items(), key=lambda v: -(v[1]["LIKE"] + v[1]["DISLIKE"]))[:12]]
    at = as_of or datetime.now(timezone.utc)
    return {
        "@timestamp": at.isoformat(), "source": "postgresql_feedback_state",
        "is_test": False,
        "current_like": like, "current_dislike": dislike,
        "current_positive_pct": round(100 * like / (like + dislike), 2) if like + dislike else None,
        "current_rating_count": rated,
        "current_rating_mean": round(sum(score * n for score, n in ratings.items()) / rated, 2) if rated else None,
        "current_excluded": excluded_count,
        "participating_playlists": len(playlists),
        "outbox_pending": outbox_pending, "projected_events": projected_events,
        "rating_distribution": [{"label": str(i) + "점", "score": i, "count": ratings[i]} for i in range(1, 6)],
        "top_positive": ranking("LIKE"), "top_negative": ranking("DISLIKE"),
        "by_method": method_rows, "by_genre": genre_rows,
    }


def django_read_only():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.cafe.settings")
    import django
    django.setup()
    from django.db import connection
    if connection.vendor != "postgresql":
        raise RuntimeError("postgresql_required")
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '5000ms'")
        cursor.execute("SET default_transaction_read_only = on")


def event_batch(cursor_value, limit, lookback_days):
    from django.db.models import Q
    from django.utils import timezone as clock
    from backend.common.models import FeedbackEvent
    query = FeedbackEvent.objects.filter(is_test=False, event_type__in=list(ACTIONS))
    if cursor_value:
        at = datetime.fromisoformat(cursor_value["at"])
        query = query.filter(Q(occurred_at__gt=at) |
                             Q(occurred_at=at, event_id__gt=cursor_value["id"]))
    else:
        query = query.filter(occurred_at__gte=clock.now()-timedelta(days=lookback_days))
    rows = list(query.order_by("occurred_at", "event_id").values(
        "event_id", "event_type", "occurred_at", "source_playlist_id", "track_id", "payload")[:limit])
    playlist_ids = {r["source_playlist_id"] for r in rows if r["source_playlist_id"]}
    from backend.recommendation.models import Playlist
    methods = dict(Playlist.objects.filter(pk__in=playlist_ids).values_list("id", "job__method"))
    return rows, methods


def current_state(limit=MAX_STATES):
    from backend.common.models import FeedbackState, FeedbackEvent, Outbox, Projection
    from backend.recommendation.models import Family
    # No Catalog.tracks or Playlist.snapshot fetches; prevent unbounded unfiltered scans.
    qs = FeedbackState.objects.filter(playlist__job__catalog__is_test=False).values(
        "target_kind", "value", "last_event_id", "playlist_id", "track_id", "playlist__job__method")
    rows = list(qs[:limit + 1])
    if len(rows) > limit:
        raise RuntimeError("state_limit_exceeded; increase capacity after index review")
    ids = {r["last_event_id"] for r in rows if r["last_event_id"]}
    metadata = {r["event_id"]: r for r in FeedbackEvent.objects.filter(
        event_id__in=ids, is_test=False).values("event_id", "payload", "is_test")}
    # A family may have many jobs; distinct prevents duplicate excluded-item totals.
    families = list(Family.objects.filter(job__catalog__is_test=False).distinct().values_list("excluded", flat=True)[:limit + 1])
    if len(families) > limit:
        raise RuntimeError("family_limit_exceeded")
    excluded = sum(len(set(items)) for items in families if isinstance(items, list))
    pending = Outbox.objects.filter(event__is_test=False).exclude(state="SENT").count()
    projected = Projection.objects.filter(event__is_test=False).count()
    return normalize_current_state(rows, metadata, excluded, pending, projected)


class Elasticsearch:
    def __init__(self, config, admin=False):
        from urllib.parse import urlsplit
        self.url = config["elasticsearch"]["url"].rstrip("/")
        url = urlsplit(self.url)
        if url.scheme != "https" or not url.hostname or url.username or url.query or url.path:
            raise ValueError("elasticsearch_https_origin_required")
        auth = config["elasticsearch"]
        name = auth["admin_user"] if admin else auth["writer_user"]
        password = auth["admin_password"] if admin else auth["writer_password"]
        self.authorization = "Basic " + base64.b64encode((name + ":" + password).encode()).decode()
        self.context = ssl.create_default_context(cafile=auth["ca_file"])

    def request(self, method, path, body=None, ndjson=False):
        if not path.startswith("/") or "//" in path or "?" in path:
            raise ValueError("invalid_elasticsearch_path")
        data = (body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()) if body is not None else None
        headers = {"Authorization": self.authorization,
                   "Content-Type": "application/x-ndjson" if ndjson else "application/json"}
        req = urllib.request.Request(self.url+path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.context, timeout=35) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError("elasticsearch_http_" + str(error.code)) from None

    def send_events(self, documents):
        if not documents:
            return
        lines = []
        for doc in documents:
            month = doc["@timestamp"][:7].replace("-", ".")
            index = "analytics-mlo-guest-events-" + month
            lines.append(json.dumps({"index": {"_index": index, "_id": doc["event_key"]}}))
            lines.append(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        response = self.request("POST", "/_bulk", ("\n".join(lines)+"\n").encode(), ndjson=True)
        if response.get("errors"):
            raise RuntimeError("elasticsearch_bulk_error; cursor_not_advanced")

    def send_state(self, summary):
        self.request("PUT", "/" + SUMMARY_INDEX + "/_doc/current", summary)


def load_cursor(path):
    if not Path(path).exists():
        return None
    value = json.loads(Path(path).read_text())
    if not (isinstance(value, dict) and "at" in value and "id" in value):
        raise RuntimeError("invalid_cursor")
    return value


def store_cursor(path, cursor):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".guest-cursor-")
    try:
        with os.fdopen(fd, "w") as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(cursor, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def run(config, dry_run=False):
    django_read_only()
    cursor = load_cursor(config["cursor_path"])
    lookback = int(config.get("initial_lookback_days", 30))
    limit = int(config.get("batch_size", 500))
    if not (1 <= lookback <= 90 and 1 <= limit <= 1000):
        raise ValueError("unsafe_exporter_bounds")
    client = None if dry_run else Elasticsearch(config)
    total = 0
    last = cursor
    for _ in range(MAX_BATCHES):
        rows, methods = event_batch(last, limit, lookback)
        if not rows:
            break
        docs = [normalize_event(row, methods.get(row["source_playlist_id"], "UNKNOWN")) for row in rows]
        docs = [doc for doc in docs if doc]
        if client:
            client.send_events(docs)
        last = {"at": rows[-1]["occurred_at"].isoformat(), "id": rows[-1]["event_id"]}
        if client:
            store_cursor(config["cursor_path"], last)  # After verified bulk ACK only.
        total += len(docs)
        if len(rows) < limit:
            break
    summary = current_state()
    if client:
        client.send_state(summary)
    return {"event_documents": total, "cursor_advanced": bool(client and last != cursor),
            "dry_run": dry_run, "current_like": summary["current_like"],
            "current_dislike": summary["current_dislike"],
            "current_rating_count": summary["current_rating_count"],
            "current_excluded": summary["current_excluded"],
            "is_test": False}


def main():
    parser = argparse.ArgumentParser(description="Read-only anonymous behavior exporter")
    parser.add_argument("--config", required=True, help="Private JSON file (never commit)")
    parser.add_argument("--dry-run", action="store_true", help="No ES write or cursor mutation")
    args = parser.parse_args()
    os.umask(0o077)
    conf = json.loads(Path(args.config).read_text())
    print(json.dumps(run(conf, dry_run=args.dry_run), ensure_ascii=False))


if __name__ == "__main__":
    main()
