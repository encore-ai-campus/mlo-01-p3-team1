"""Versioned occasion screening kept separate from the original music fields.

GENERAL means no event signal in the inspected metadata, not listening approval.
Snow/winter and artist names alone never trigger an event exclusion or hold.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from typing import Mapping

POLICY_VERSION = "OCCASION_GENERAL_20261016_V1"
STATUSES = frozenset({"GENERAL", "SEASONAL_EVENT", "REVIEW_REQUIRED", "UNSCREENED"})

# Explicit event wording, with word boundaries for Latin-script expressions.
EVENT_PATTERNS = {
    "CHRISTMAS": (r"\bchristmas\b", r"\bx[ -]?mas\b", r"크리스마스", r"성탄", r"聖誕|圣诞", r"\bfeliz navidad\b", r"\bweihnacht\w*\b", r"\bnatale\b", r"\bno[eë]l de\b"),
    "HALLOWEEN": (r"\bhalloween\b", r"할로윈|핼러윈"),
    "NEW_YEAR": (r"\bhappy new year\b", r"\bnew year(?:'s)? (?:eve|day)\b", r"새해 복 많이", r"신년 축하"),
    "BIRTHDAY": (r"\bhappy birthday\b", r"생일 축하|생일축하"),
}

# Ambiguous hymn/carol titles require another event cue or manual verification.
CAROL_TITLES = (
    "sleigh ride", "jingle bells", "jingle bell rock", "silent night",
    "joy to the world", "deck the halls", "o holy night", "the first noel",
    "little drummer boy", "rudolph the red nosed reindeer", "auld lang syne",
    "hark the herald angels sing", "o come all ye faithful", "o tannenbaum",
)

# Specific title + named performer/version rules. These are reviewable initial
# rules, not a learned classifier or evidence that every recording was heard.
RECORDING_RULES = (
    ("sleigh ride", "ella fitzgerald", "CHRISTMAS"),
    ("joy to the world", "nat king cole", "CHRISTMAS"),
)


def normalize(value: object) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    return " ".join(value.split())


def event_codes(text: str) -> list[str]:
    return sorted(code for code, expressions in EVENT_PATTERNS.items()
                  if any(re.search(expression, text) for expression in expressions))


def title_key(title: str) -> str:
    # Version subtitles stay in the evidence; punctuation is normalized solely
    # for conservative title-prefix comparisons.
    return " ".join(re.sub(r"[^\w\s]", " ", title, flags=re.UNICODE).split())


def carol_matches(title: str) -> list[str]:
    key = title_key(title)
    return [name for name in CAROL_TITLES
            if key == name or key.startswith(name + " ")]


@dataclass(frozen=True)
class OccasionDecision:
    track_id: str
    occasion_status: str
    decision_source: str
    occasion_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence: tuple[str, ...]
    occasion_decision_version: str
    occasion_policy_version: str = POLICY_VERSION

    def as_row(self) -> dict[str, str]:
        return {"track_id": self.track_id, "occasion_status": self.occasion_status,
                "decision_source": self.decision_source,
                "occasion_codes": ";".join(self.occasion_codes),
                "occasion_reasons": ";".join(self.reasons),
                "occasion_evidence": json.dumps(self.evidence, ensure_ascii=False),
                "occasion_policy_version": self.occasion_policy_version,
                "occasion_decision_version": self.occasion_decision_version}


def _decision(track_id: str, status: str, source: str, codes=(), reasons=(), evidence=()) -> OccasionDecision:
    payload = [POLICY_VERSION, track_id, status, source, sorted(set(codes)), list(reasons), list(evidence)]
    version = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return OccasionDecision(track_id, status, source, tuple(sorted(set(codes))),
                            tuple(reasons), tuple(evidence), version)


def screen_track(track: Mapping[str, object], override: Mapping[str, object] | None = None,
                 source_sha256: str | None = None) -> OccasionDecision:
    """Inspect title/album; optional explicit human decision has precedence."""
    track_id = str(track.get("track_id") or "").strip()
    if not track_id:
        raise ValueError("track_id is required")
    if override is not None:
        status = override.get("occasion_status")
        codes = override.get("occasion_codes", [])
        if (status not in STATUSES or not override.get("reviewer") or not override.get("evidence")
                or not override.get("reviewed_at") or not source_sha256
                or override.get("source_dataset_sha256") != source_sha256
                or not isinstance(codes, list) or not all(isinstance(code, str) and code for code in codes)
                or (status == "SEASONAL_EVENT" and not codes)):
            raise ValueError(f"invalid or stale human override: {track_id}")
        return _decision(track_id, str(status), "HUMAN_REVIEW", codes,
                         ["EXPLICIT_HUMAN_REVIEW"], [str(override["evidence"]),
                         "reviewer=" + str(override["reviewer"]), "reviewed_at=" + str(override["reviewed_at"])])

    fields = {name: normalize(track.get(name)) for name in ("track_name", "album_name")}
    artists = normalize(track.get("artists") or track.get("artists_name"))
    if not all(fields.values()) or not artists or track.get("metadata_conflict"):
        return _decision(track_id, "UNSCREENED", "RULE_SCREEN", reasons=["MISSING_OR_CONFLICTING_METADATA"])
    title, album = fields["track_name"], fields["album_name"]
    title_events, album_events = event_codes(title), event_codes(album)
    evidence = ["track_name=" + str(track["track_name"]), "album_name=" + str(track["album_name"])]
    if title_events:
        return _decision(track_id, "SEASONAL_EVENT", "APPROVED_RULE", title_events,
                         ["EXPLICIT_EVENT_PHRASE_IN_TITLE"], evidence)
    carols = carol_matches(title)
    for song, performer, event in RECORDING_RULES:
        if song in carols and performer in [normalize(name) for name in artists.split(";")]:
            return _decision(track_id, "SEASONAL_EVENT", "APPROVED_RULE", [event],
                             ["KNOWN_TITLE_AND_PERFORMER_RULE"], evidence + ["artists=" + artists])
    if carols and album_events:
        return _decision(track_id, "SEASONAL_EVENT", "APPROVED_RULE", album_events,
                         ["CAROL_TITLE_AND_EXPLICIT_EVENT_ALBUM"], evidence)
    if carols or album_events:
        return _decision(track_id, "REVIEW_REQUIRED", "RULE_SCREEN", album_events,
                         ["AMBIGUOUS_CAROL_TITLE" if carols else "EVENT_ALBUM_ONLY"], evidence)
    return _decision(track_id, "GENERAL", "RULE_SCREEN", reasons=["NO_EVENT_SIGNAL_IN_METADATA"], evidence=evidence)


def policy_document() -> dict:
    return {"occasion_policy_version": POLICY_VERSION,
            "statuses": sorted(STATUSES), "general_eligible_status": "GENERAL",
            "event_expressions": EVENT_PATTERNS, "ambiguous_carol_titles": CAROL_TITLES,
            "recording_rules": RECORDING_RULES,
            "unknown_means_general": False, "no_signal_means_listening_approval": False,
            "snow_winter_artist_name_alone_is_event_signal": False,
            "automatic_event_calendar_allowance": False,
            "human_override_requires_source_sha256": True}
