"""Offline unit + loopback HTTP integration tests. No YouTube API requests."""
import csv
import importlib.util
import json
import shutil
import threading
import unittest
from uuid import uuid4
from http.client import HTTPConnection
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("youtube_prototype_server", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LocalPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.root = FILE.parent / "tests" / ".test-tmp" / str(uuid4())
        self.root.mkdir(parents=True)
        self.data = self.root / "data"
        (self.data / "examples").mkdir(parents=True)
        self.row = {"position": "1", "track_id": "fixture-track", "track_name": "Fixture Song", "artists": "Fixture Artist", "album_name": "Fixture Album", "duration_ms": "180000", "occasion_status": "GENERAL", "energy": "0.50000", "occasion_policy_version": "FIXTURE_V1", "occasion_decision_version": "fixture-d1"}
        self.write_source(self.row)
        self.store = module.PlaylistStore(self.data, self.root / "mapping.json")
        self.server = module.LocalServer(0, self.store, module.SearchProvider(None))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        # Verify the recursive cleanup target is an exact child of our test workspace.
        self.root.resolve().relative_to((FILE.parent / "tests" / ".test-tmp").resolve())
        shutil.rmtree(self.root)

    def write_source(self, row):
        with (self.data / "examples/CLEAR_180min.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

    def mapping(self):
        return {"track_id": "fixture-track", "youtube_video_id": "testVID0001", "youtube_title": "Fixture Video", "youtube_channel": "Fixture Channel", "platform_duration_seconds": 180, "match_status": "VERIFIED", "verification_note": "UNIT FIXTURE ONLY; not a real verified video", "verified_by": "UNIT_TEST", "checked_at": "2026-10-16T00:00:00+00:00", "match_method": "UNIT_TEST"}

    def call(self, method, path, value=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = headers or {}
        body = json.dumps(value) if value is not None else None
        if body:
            h = {"Content-Type": "application/json", **h}
        connection.request(method, path, body=body, headers=h)
        response = connection.getresponse()
        content = response.read()
        result = (response.status, dict(response.headers), content)
        connection.close()
        return result

    def protected_headers(self):
        return {"Origin": self.origin, "X-Local-Nonce": self.server.nonce}

    def import_payload(self, mapping=None):
        return {"expected_mapping_version": self.store.mappings()[1], "mappings": [mapping or self.mapping()]}

    def test_source_roundtrip_and_general_mapping_gate(self):
        before = self.store.playlist("CLEAR")
        self.assertFalse(before["tracks"][0]["playable"])
        self.assertEqual(before["tracks"][0]["source_fields"], self.row)
        self.store.import_mappings(self.import_payload())
        after = self.store.playlist("CLEAR")
        self.assertTrue(after["tracks"][0]["playable"])
        self.assertEqual(after["tracks"][0]["source_fields"], self.row)
        self.assertEqual(after["source_readiness"], "ANALYSIS_ONLY_NOT_READY")
        self.assertNotEqual(before["queue_version"], after["queue_version"])

    def test_missing_or_seasonal_status_never_becomes_playable(self):
        self.store.import_mappings(self.import_payload())
        for status in ("UNSCREENED", "REVIEW_REQUIRED", "SEASONAL_EVENT", "OTHER", ""):
            self.write_source({**self.row, "occasion_status": status})
            self.assertFalse(self.store.playlist("CLEAR")["tracks"][0]["playable"])

    def test_verified_requires_length_evidence_and_real_shape(self):
        for change in ({"platform_duration_seconds": 0}, {"platform_duration_seconds": True}, {"platform_duration_seconds": float("nan")}, {"verification_note": ""}, {"youtube_video_id": "invented"}, {"checked_at": "2026-10-16"}):
            with self.assertRaises(module.InputError):
                self.store.import_mappings(self.import_payload({**self.mapping(), **change}))
        self.assertFalse(self.store.mapping_file.exists())

    def test_batch_is_atomic_and_stale_revision_is_conflict(self):
        payload = self.import_payload()
        bad = {**self.mapping(), "track_id": "missing"}
        with self.assertRaises(module.InputError):
            self.store.import_mappings({**payload, "mappings": [self.mapping(), bad]})
        self.assertFalse(self.store.mapping_file.exists())
        self.store.import_mappings(payload)
        with self.assertRaises(module.ConflictError):
            self.store.import_mappings(payload)

    def test_idempotent_same_mapping_keeps_version_and_source_change_holds(self):
        self.store.import_mappings(self.import_payload())
        old = self.store.mappings()[1]
        self.store.import_mappings(self.import_payload())
        self.assertEqual(self.store.mappings()[1], old)
        self.write_source({**self.row, "track_name": "Different Version"})
        self.assertFalse(self.store.playlist("CLEAR")["tracks"][0]["playable"])

    def test_http_nonce_and_origin_gate(self):
        payload = self.import_payload()
        for headers in ({}, {"X-Local-Nonce": self.server.nonce}, {"Origin": "https://foreign.example", "X-Local-Nonce": self.server.nonce}, {"Origin": self.origin, "X-Local-Nonce": "wrong"}):
            self.assertEqual(self.call("POST", "/api/mappings/import", payload, headers)[0], 403)
        self.assertFalse(self.store.mapping_file.exists())
        self.assertEqual(self.call("POST", "/api/mappings/import", payload, self.protected_headers())[0], 200)

    def test_get_search_accepts_browser_same_origin_without_origin_header(self):
        self.server.search.search = lambda source: {"track_id": source["track_id"], "candidates": []}
        headers = {"X-Local-Nonce": self.server.nonce, "Sec-Fetch-Site": "same-origin"}
        self.assertEqual(self.call("GET", "/api/youtube/search?track_id=fixture-track", headers=headers)[0], 200)
        self.assertEqual(self.call("GET", "/api/youtube/search?track_id=fixture-track", headers={"X-Local-Nonce": self.server.nonce})[0], 403)
        self.assertEqual(self.call("GET", "/api/youtube/search?track_id=fixture-track", headers={**headers, "Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_static_allowlist_rebinding_and_headers(self):
        status, headers, _ = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        for path in ("/server.py", "/../AGENTS.md", "/data/mapping.json", "/logs/events.jsonl"):
            self.assertEqual(self.call("GET", path)[0], 404)
        self.assertEqual(self.call("GET", "/api/config", headers={"Host": "attacker.example"})[0], 403)

    def test_optional_search_filters_and_cache_without_real_network(self):
        provider = module.SearchProvider("UNIT_TEST_NOT_A_KEY")
        calls = []
        def fake(endpoint, parameters):
            calls.append(endpoint)
            if endpoint == "search":
                return {"items": [{"id": {"videoId": "testVID0001"}}, {"id": {"videoId": "testVID0002"}}]}
            return {"items": [
                {"id": "testVID0001", "snippet": {"title": "Fixture", "channelTitle": "Unit", "liveBroadcastContent": "none"}, "status": {"embeddable": True}, "contentDetails": {"duration": "PT3M"}},
                {"id": "testVID0002", "snippet": {}, "status": {"embeddable": True}, "contentDetails": {"duration": "PT3M", "regionRestriction": {"blocked": ["KR"]}}},
            ]}
        provider.request = fake
        first = provider.search(self.row)
        second = provider.search(self.row)
        self.assertEqual(first, second)
        self.assertEqual(calls, ["search", "videos"])
        self.assertEqual(len(first["candidates"]), 1)
        self.assertEqual(first["candidates"][0]["match_status"], "CANDIDATE")


if __name__ == "__main__":
    unittest.main()
