import hashlib
import json
from unittest.mock import patch
from django.test import TestCase
from backend.music.catalog import publish
from backend.recommendation.catalog_storage import unpack
from backend.recommendation.errors import DomainError
from backend.recommendation.models import Catalog
from backend.recommendation.worker import verified_catalog


class CatalogStorageTests(TestCase):
    def test_large_published_catalog_keeps_exact_tracks_and_digest(self):
        tracks = [{'track_id': 'large-track', 'track_name': '검수된 음악' * 150000,
                   'genre_group_codes': ['JAZZ'], 'speed': 'medium', 'energy': 3,
                   'duration_ms': 240000, 'mode': True,
                   'occasion_status':'GENERAL','decision_source':'RULE_SCREEN',
                   'occasion_policy_version':'fixture-v1','occasion_decision_version':'fixture-decision'}]
        with patch('backend.music.catalog.export_tracks', return_value=iter(tracks)):
            catalog = publish('compressed-source', 'music-source:' + 'a' * 64, 'a' * 64)
        self.assertIsInstance(catalog.tracks, dict)
        self.assertLess(len(json.dumps(catalog.tracks)), 100000)
        expected = unpack(catalog.tracks)
        self.assertEqual(expected[0]['track_name'], tracks[0]['track_name'])
        self.assertEqual(catalog.sha256, hashlib.sha256(json.dumps(expected, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
        self.assertEqual(verified_catalog(catalog), expected)

    def test_corrupt_compressed_catalog_fails_integrity_validation(self):
        from backend.recommendation.catalog_storage import pack
        tracks = [{'track_id': 'corrupt-track', 'track_name': 'a' * 1100000}]
        stored, digest = pack(tracks)
        stored['data'] = stored['data'][:-4]
        catalog = Catalog.objects.create(version='corrupt-compressed', tracks=stored, sha256=digest, ready=True)
        with self.assertRaises(DomainError) as error:
            verified_catalog(catalog)
        self.assertEqual(error.exception.code, 'CATALOG_INVALID')

    def test_legacy_list_and_bounded_expansion(self):
        from backend.recommendation.catalog_storage import pack
        rows = [{'track_id': 'legacy'}]
        catalog = Catalog.objects.create(version='legacy-list', tracks=rows,
            sha256=hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), ready=True)
        self.assertEqual(verified_catalog(catalog), rows)
        stored, _ = pack([{'track_id': 'bounded', 'track_name': 'a' * 1100000}])
        stored['uncompressed_bytes'] = 10
        with self.assertRaises(ValueError):
            unpack(stored)
