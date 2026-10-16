"""Loopback-only YouTube playback prototype. No production DB or login dependency."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

APP_DIR = Path(__file__).resolve().parent
REPO_DIR = APP_DIR.parents[1]
WEATHERS = {"CLEAR": "맑음", "CLOUDY": "구름낌", "OVERCAST": "흐림", "RAIN": "비", "SNOW": "눈"}
STATUSES = {"UNRESOLVED", "CANDIDATE", "VERIFIED", "REJECTED", "UNAVAILABLE", "BLOCKED_EMBED"}
OCCASIONS = {"GENERAL", "SEASONAL_EVENT", "REVIEW_REQUIRED", "UNSCREENED"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
MAX_BODY = 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class InputError(ValueError):
    pass


class ConflictError(InputError):
    pass


class PlaylistStore:
    def __init__(self, data_dir: Path, mapping_file: Path):
        self.data_dir = data_dir.resolve()
        self.mapping_file = mapping_file.resolve()
        self.lock = threading.RLock()

    def source(self, weather: str) -> tuple[list[dict], str]:
        if weather not in WEATHERS:
            raise InputError("지원하지 않는 날씨입니다.")
        path = self.data_dir / "examples" / f"{weather}_180min.csv"
        if not path.is_file():
            raise InputError("일반곡 선곡표가 아직 없습니다. --data-dir 및 데이터 생성 결과를 확인해 주세요.")
        content = path.read_bytes()
        rows = list(csv.DictReader(content.decode("utf-8-sig").splitlines(keepends=True)))
        seen = set()
        for index, row in enumerate(rows, 1):
            if not all(row.get(k) for k in ("track_id", "track_name", "artists", "album_name")):
                raise InputError("선곡표 필수 메타데이터가 누락되었습니다.")
            try:
                valid = int(row["position"]) == index and int(row["duration_ms"]) > 0
            except (ValueError, KeyError, TypeError):
                valid = False
            if not valid or row["track_id"] in seen:
                raise InputError("선곡표 순번·길이·중복 ID 검증에 실패했습니다.")
            seen.add(row["track_id"])
        if not rows:
            raise InputError("비어 있는 선곡표입니다.")
        return rows, hashlib.sha256(content).hexdigest()

    def mappings(self) -> tuple[dict[str, dict], str]:
        with self.lock:
            if not self.mapping_file.exists():
                return {}, digest([])
            try:
                value = json.loads(self.mapping_file.read_text(encoding="utf-8-sig"))
                records = value["mappings"]
                if not isinstance(records, list):
                    raise ValueError()
                by_id = {r["track_id"]: r for r in records}
                if len(by_id) != len(records):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise InputError("매핑 파일을 읽지 못했습니다. 기존 파일은 보존됩니다.") from None
            return by_id, digest(sorted(records, key=lambda r: r["track_id"]))

    def known_tracks(self) -> dict[str, dict]:
        result = {}
        for weather in WEATHERS:
            try:
                rows, _ = self.source(weather)
            except InputError:
                continue
            for row in rows:
                result[row["track_id"]] = row
        return result

    @staticmethod
    def validate_mapping(record: dict, source: dict) -> dict:
        if not isinstance(record, dict):
            raise InputError("매핑 항목은 객체여야 합니다.")
        status = record.get("match_status", "CANDIDATE")
        if not isinstance(status, str) or status not in STATUSES:
            raise InputError("허용하지 않는 매핑 상태입니다.")
        if source.get("occasion_status", "UNSCREENED") != "GENERAL":
            raise InputError("GENERAL 곡만 영상 매핑을 등록할 수 있습니다.")
        for field, source_field in (("source_track_name", "track_name"), ("source_artists", "artists"), ("source_album_name", "album_name")):
            if field in record and record[field] != source[source_field]:
                raise InputError("매핑의 원곡 메타데이터가 현재 입력과 다릅니다. 다시 검수해 주세요.")
        if "source_duration_ms" in record and record["source_duration_ms"] != int(source["duration_ms"]):
            raise InputError("매핑의 원곡 길이가 현재 입력과 다릅니다.")
        video_id = record.get("youtube_video_id")
        if video_id is not None and (not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id)):
            raise InputError("영상 ID는 실제 영상의 11자 ID를 입력해 주세요.")
        duration = record.get("platform_duration_seconds")
        if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0):
            raise InputError("확인한 영상 길이는 양수여야 합니다.")
        for field in ("youtube_title", "youtube_channel", "verification_note", "verified_by", "checked_at", "match_method"):
            if record.get(field) is not None and (not isinstance(record[field], str) or len(record[field]) > 4000):
                raise InputError("매핑 텍스트 필드가 올바르지 않습니다.")
        if status == "VERIFIED":
            required = ("youtube_title", "youtube_channel", "verification_note", "verified_by", "checked_at")
            if not video_id or not duration or not all(str(record.get(k) or "").strip() for k in required):
                raise InputError("확정에는 실제 ID·영상 길이·제목·채널·확인 근거·검수자·시각이 필요합니다.")
            try:
                checked = datetime.fromisoformat(record["checked_at"].replace("Z", "+00:00"))
                if checked.tzinfo is None:
                    raise ValueError()
            except ValueError:
                raise InputError("확인 시각은 시간대가 있는 ISO8601이어야 합니다.") from None
        normalized = {k: record.get(k) for k in ("youtube_video_id", "youtube_title", "youtube_channel", "platform_duration_seconds", "verification_note", "verified_by", "checked_at", "match_method")}
        normalized.update(track_id=source["track_id"], source_track_name=source["track_name"], source_artists=source["artists"], source_album_name=source["album_name"], source_duration_ms=int(source["duration_ms"]), match_status=status)
        normalized["mapping_version"] = digest(normalized)
        return normalized

    def import_mappings(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("mappings"), list) or not payload["mappings"] or len(payload["mappings"]) > 500:
            raise InputError("mappings 배열에 1~500개 항목을 입력해 주세요.")
        with self.lock:
            existing, old_version = self.mappings()
            if payload.get("expected_mapping_version") != old_version:
                raise ConflictError("매핑이 다른 화면에서 변경되었습니다. 목록을 새로 불러와 주세요.")
            known = self.known_tracks()
            updates = {}
            for record in payload["mappings"]:
                if not isinstance(record, dict) or record.get("track_id") not in known:
                    raise InputError("현재 선곡표에 없는 곡 ID입니다.")
                track_id = record["track_id"]
                if track_id in updates:
                    raise InputError("가져올 매핑에 같은 곡이 중복되었습니다.")
                updates[track_id] = self.validate_mapping(record, known[track_id])
            existing.update(updates)
            records = sorted(existing.values(), key=lambda r: r["track_id"])
            version = digest(records)
            output = {"schema_version": "YOUTUBE_MAPPING_V1", "mapping_version": version, "updated_at": utc_now(), "mappings": records}
            self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.mapping_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.mapping_file)
            return {"saved_count": len(updates), "mapping_version": version}

    def playlist(self, weather: str) -> dict:
        rows, csv_hash = self.source(weather)
        mappings, mapping_version = self.mappings()
        tracks = []
        for row in rows:
            occasion = row.get("occasion_status", "UNSCREENED")
            if occasion not in OCCASIONS:
                occasion = "UNSCREENED"
            mapping = mappings.get(row["track_id"])
            # Even manually edited sidecars must pass the same import validation.
            if mapping:
                try:
                    mapping = self.validate_mapping(mapping, row)
                except InputError:
                    mapping = None
            playable = occasion == "GENERAL" and mapping is not None and mapping.get("match_status") == "VERIFIED" and bool(mapping.get("platform_duration_seconds"))
            tracks.append({"source_position": int(row["position"]), "track_id": row["track_id"], "track_name": row["track_name"], "artists": row["artists"], "album_name": row["album_name"], "duration_ms": int(row["duration_ms"]), "occasion_status": occasion, "source_fields": dict(row), "mapping": mapping, "playable": playable})
        queue_version = digest({"weather": weather, "source_csv_sha256": csv_hash, "mapping_version": mapping_version})
        count = sum(t["playable"] for t in tracks)
        return {"schema_version": "YOUTUBE_LOCAL_PLAYBACK_DEMO_V1", "queue_version": queue_version, "mapping_version": mapping_version, "weather": weather, "weather_label": WEATHERS[weather], "source_readiness": "ANALYSIS_ONLY_NOT_READY", "source_csv_sha256": csv_hash, "occasion_policy_versions": sorted({r.get("occasion_policy_version", "UNSCREENED") for r in rows}), "occasion_decision_versions": sorted({r.get("occasion_decision_version", "UNSCREENED") for r in rows}), "track_count": len(tracks), "playable_count": count, "source_total_ms": sum(t["duration_ms"] for t in tracks), "platform_total_seconds": sum(t["mapping"]["platform_duration_seconds"] for t in tracks) if count == len(tracks) else None, "tracks": tracks}

    def listing(self) -> dict:
        entries = []
        for weather, label in WEATHERS.items():
            try:
                queue = self.playlist(weather)
                entries.append({k: queue[k] for k in ("weather", "weather_label", "track_count", "playable_count", "source_total_ms")})
            except InputError as error:
                entries.append({"weather": weather, "weather_label": label, "error": str(error)})
        return {"playlists": entries, "source_readiness": "ANALYSIS_ONLY_NOT_READY"}


def iso_duration(value: str) -> float:
    match = re.fullmatch(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value)
    if not match:
        return 0
    days, hours, minutes, seconds = (float(v or 0) for v in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class SearchProvider:
    """Optional official Data API. Search results never become VERIFIED automatically."""
    def __init__(self, api_key: str | None):
        self.api_key = api_key
        self.cache = {}
        self.lock = threading.Lock()
        self.daily_count = 0
        self.day = ""

    def request(self, endpoint: str, parameters: dict) -> dict:
        url = "https://www.googleapis.com/youtube/v3/" + endpoint + "?" + urlencode({**parameters, "key": self.api_key})
        try:
            with urlopen(url, timeout=15) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError):
            # Do not log URLs or exceptions, which could contain the server-only key.
            raise InputError("YouTube 검색에 실패했습니다. API 설정·실제 할당을 확인하거나 수동 검색해 주세요.") from None

    def search(self, source: dict) -> dict:
        if not self.api_key:
            raise InputError("검색 API 키가 없습니다. 수동 검색과 매핑 등록을 이용해 주세요.")
        track_id = source["track_id"]
        with self.lock:
            cached = self.cache.get(track_id)
            if cached and time.time() - cached[0] < 900:
                return cached[1]
            day = datetime.now(timezone.utc).date().isoformat()
            if self.day != day:
                self.day, self.daily_count = day, 0
            if self.daily_count >= 100:
                raise InputError("이 프로세스의 검색 안전 상한에 도달했습니다. 실제 할당은 Cloud Console에서 확인해 주세요.")
            self.daily_count += 1
            search = self.request("search", {"part": "snippet", "q": f'{source["track_name"]} {source["artists"]} {source["album_name"]}', "type": "video", "videoEmbeddable": "true", "videoSyndicated": "true", "regionCode": "KR", "maxResults": 5})
            ids = [r.get("id", {}).get("videoId") for r in search.get("items", [])]
            ids = [i for i in ids if i and VIDEO_ID.fullmatch(i)]
            result = {"track_id": track_id, "candidates": [], "search_calls_this_process_day": self.daily_count}
            if ids:
                videos = self.request("videos", {"part": "snippet,contentDetails,status", "id": ",".join(ids)})
                for video in videos.get("items", []):
                    snippet, details = video.get("snippet", {}), video.get("contentDetails", {})
                    region = details.get("regionRestriction", {})
                    duration = iso_duration(details.get("duration", ""))
                    if not video.get("status", {}).get("embeddable") or "KR" in region.get("blocked", []) or ("allowed" in region and "KR" not in region["allowed"]) or snippet.get("liveBroadcastContent", "none") != "none" or duration <= 0:
                        continue
                    result["candidates"].append({"youtube_video_id": video["id"], "youtube_title": snippet.get("title", ""), "youtube_channel": snippet.get("channelTitle", ""), "platform_duration_seconds": duration, "match_status": "CANDIDATE"})
            self.cache[track_id] = (time.time(), result)
            return result


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, store: PlaylistStore, search: SearchProvider):
        self.store, self.search = store, search
        self.nonce = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def log_message(self, format: str, *args: object) -> None:
        pass

    def local_origin(self) -> str | None:
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return None
        origin = f"http://{host}"
        if self.headers.get("Origin") not in (None, origin) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            return None
        return origin

    def headers_for(self, status: int, kind: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' https://www.youtube.com https://s.ytimg.com; frame-src https://www.youtube.com; connect-src 'self'; style-src 'self'; img-src 'self' https://i.ytimg.com; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Permissions-Policy", 'autoplay=(self "https://www.youtube.com")')
        self.end_headers()

    def send_json(self, status: int, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.headers_for(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def protected(self, *, read: bool = False) -> bool:
        origin = self.local_origin()
        origin_matches = self.headers.get("Origin") == origin
        same_origin_get = read and self.headers.get("Origin") is None and self.headers.get("Sec-Fetch-Site") == "same-origin"
        return bool(origin and (origin_matches or same_origin_get) and secrets.compare_digest(self.headers.get("X-Local-Nonce", ""), self.server.nonce))

    def do_GET(self) -> None:
        if not self.local_origin():
            self.send_json(403, {"error": "로컬 출처에서만 접근할 수 있습니다."})
            return
        path = urlsplit(self.path)
        try:
            if path.path == "/api/config":
                self.send_json(200, {"nonce": self.server.nonce, "search_enabled": bool(self.server.search.api_key), "source_readiness": "ANALYSIS_ONLY_NOT_READY"})
            elif path.path == "/api/playlists":
                self.send_json(200, self.server.store.listing())
            elif path.path.startswith("/api/playlists/"):
                self.send_json(200, self.server.store.playlist(path.path.split("/")[-1]))
            elif path.path == "/api/youtube/search":
                if not self.protected(read=True):
                    self.send_json(403, {"error": "출처와 로컬 접근 코드를 확인해 주세요."})
                    return
                track_id = parse_qs(path.query).get("track_id", [""])[0]
                source = self.server.store.known_tracks().get(track_id)
                if not source or source.get("occasion_status") != "GENERAL":
                    raise InputError("현재 일반 선곡표의 곡만 검색할 수 있습니다.")
                self.send_json(200, self.server.search.search(source))
            else:
                allowed = {"/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/queue.mjs": ("queue.mjs", "text/javascript"), "/styles.css": ("styles.css", "text/css")}
                if path.path not in allowed:
                    self.send_json(404, {"error": "없는 경로입니다."})
                    return
                name, kind = allowed[path.path]
                data = (APP_DIR / "web" / name).read_bytes()
                self.headers_for(200, kind + "; charset=utf-8", len(data))
                self.wfile.write(data)
        except InputError as error:
            self.send_json(422, {"error": str(error)})
        except OSError:
            self.send_json(500, {"error": "파일을 읽지 못했습니다. 입력·권한을 확인해 주세요."})

    def do_POST(self) -> None:
        if not self.protected():
            self.send_json(403, {"error": "상태 변경은 같은 출처와 로컬 접근 코드가 필요합니다."})
            return
        if self.path != "/api/mappings/import":
            self.send_json(404, {"error": "없는 경로입니다."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise InputError("1MiB 이하의 JSON 입력이 필요합니다.")
            payload = json.loads(self.rfile.read(length))
            self.send_json(200, self.server.store.import_mappings(payload))
        except ConflictError as error:
            self.send_json(409, {"error": str(error)})
        except (ValueError, TypeError) as error:
            self.send_json(422, {"error": str(error) if isinstance(error, InputError) else "JSON 입력을 확인해 주세요."})
        except OSError:
            self.send_json(500, {"error": "매핑 저장에 실패했습니다. 기존 파일과 입력을 확인해 주세요."})


def main() -> None:
    parser = argparse.ArgumentParser(description="일반곡 CSV와 검수 영상 매핑의 로컬 YouTube 재생 시험")
    parser.add_argument("--data-dir", type=Path, default=REPO_DIR / "analysis/weather_music_20261016/general")
    parser.add_argument("--mapping-file", type=Path, default=APP_DIR / "data/mapping.json")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("포트는 0~65535여야 합니다.")
    server = LocalServer(args.port, PlaylistStore(args.data_dir, args.mapping_file), SearchProvider(os.environ.get("YOUTUBE_DATA_API_KEY")))
    print(f"YouTube 로컬 시험: http://127.0.0.1:{server.server_address[1]}/", flush=True)
    print("분석 자료 시험용입니다. 계정·Premium·실제 소리·장시간 재생은 브라우저에서 별도 확인합니다.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
