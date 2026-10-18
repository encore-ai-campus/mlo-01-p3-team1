from copy import deepcopy
from io import BytesIO
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from backend.recommendation.errors import DomainError
from backend.recommendation.youtube_playback import (
    SearchFailure, _api_json, _duration, _match_candidate,
    resolve_playback_candidates, validate_playback_request,
)


def track(**changes):
    return {'track_id': 'source-track', 'track_name': 'Golden Morning', 'artists_name': 'Artist One;Guest',
            'album_name': 'Original Album', 'duration_ms': 240_000, **changes}


def video(video_id='abcdefghijk', **changes):
    result = {'id': video_id,
              'snippet': {'title': 'Artist One - Golden Morning (Official Audio)',
                          'channelTitle': 'Artist One - Topic', 'liveBroadcastContent': 'none',
                          'description': 'Provided to YouTube by original record label'},
              'contentDetails': {'duration': 'PT4M', 'regionRestriction': {'allowed': ['KR', 'US']}},
              'status': {'embeddable': True, 'privacyStatus': 'public'}}
    for section, values in changes.items():
        result[section].update(values)
    return result


@override_settings(YOUTUBE_PLAYBACK_MODE='OPTIONAL_SEARCH', YOUTUBE_DATA_API_KEY='test-key-no-network',
                   YOUTUBE_SEARCH_PER_OWNER_MINUTE=6, YOUTUBE_SEARCH_DAILY_LIMIT=80,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                                       'LOCATION': 'youtube-playback-unit-tests'}})
class YoutubePlaybackTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def mapped_track(self):
        return track(youtube_video_id='mapped12345', youtube_match_status='VERIFIED',
                     youtube_mapping_snapshot={'youtube_title': 'Golden Morning',
                         'youtube_channel': 'Artist One - Topic', 'platform_duration_seconds': 241})

    def search_payload(self, ids=('abcdefghijk',)):
        return [{'id': {'videoId': value}} for value in ids]

    def test_request_shape_rejects_urls_keys_unknown_fields_and_invalid_exclusions(self):
        self.assertEqual(validate_playback_request({'track_id': 'x'}), ('x', []))
        ids = [f'abcdefghij{i}' for i in range(10)]
        self.assertEqual(validate_playback_request({'track_id': 'x', 'excluded_video_ids': ids}), ('x', ids))
        for body in [None, [], {}, {'track_id': ''}, {'track_id': 3}, {'track_id': 'x', 'query': 'anything'},
                     {'track_id': 'x', 'url': 'https://example.com/'}, {'track_id': 'x', 'api_key': 'secret'},
                     {'track_id': 'x', 'excluded_video_ids': 'abcdefghijk'},
                     {'track_id': 'x', 'excluded_video_ids': ['not-an-id']},
                     {'track_id': 'x', 'excluded_video_ids': ['abcdefghijk', 'abcdefghijk']},
                     {'track_id': 'x', 'excluded_video_ids': ids + ['abcdefghijk']}]:
            with self.subTest(body=body), self.assertRaises(DomainError) as failure:
                validate_playback_request(body)
            self.assertEqual(failure.exception.status, 422)

    @override_settings(YOUTUBE_DATA_API_KEY='')
    def test_verified_mapping_works_without_key_and_never_calls_search(self):
        original = self.mapped_track()
        before = deepcopy(original)
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=AssertionError('unexpected network')):
            result = resolve_playback_candidates(original)
        self.assertEqual(original, before)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['candidates'][0]['source'], 'CATALOG_MAPPING')
        self.assertEqual(result['candidates'][0]['duration_seconds'], 241)

    @override_settings(YOUTUBE_DATA_API_KEY='')
    def test_unmapped_or_failed_mapping_without_key_is_explicitly_unavailable(self):
        for original, excluded in [(track(), []), (self.mapped_track(), ['mapped12345']),
                                    (track(youtube_match_status='CANDIDATE', youtube_video_id='abcdefghijk'), [])]:
            result = resolve_playback_candidates(original, excluded)
            self.assertEqual(result['status'], 'SEARCH_UNAVAILABLE')
            self.assertEqual(result['reason'], 'API_KEY_MISSING')
            self.assertEqual(result['candidates'], [])

    def test_duration_parser_is_bounded_to_positive_iso_time(self):
        self.assertEqual(_duration('PT1H2M3.5S'), 3723.5)
        self.assertEqual(_duration('PT4M'), 240)
        for value in ('', 'PT', 'PT0S', 'not-duration', 'P1D'):
            self.assertIsNone(_duration(value))

    def test_api_search_uses_fixed_filters_and_keeps_automatic_match_as_candidate(self):
        source = track()
        before = deepcopy(source)
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=[self.search_payload(), [video()]]) as request:
            result = resolve_playback_candidates(source, owner_id='owner')
        self.assertEqual(source, before)
        self.assertEqual(result['status'], 'READY')
        candidate = result['candidates'][0]
        self.assertEqual(candidate['match_status'], 'CANDIDATE')
        self.assertEqual(candidate['source'], 'YOUTUBE_API')
        self.assertNotIn('_score', candidate)
        self.assertEqual(request.call_count, 2)
        parameters = request.call_args_list[0].args[1]
        self.assertEqual(parameters['q'], 'Golden Morning Artist One Guest')
        self.assertEqual(parameters['type'], 'video')
        self.assertEqual(parameters['videoEmbeddable'], 'true')
        self.assertEqual(parameters['videoSyndicated'], 'true')
        self.assertEqual(parameters['regionCode'], 'KR')
        self.assertEqual(parameters['maxResults'], 5)

    def test_title_artist_version_and_duration_reject_false_matches(self):
        candidates = [video(snippet={'title': 'Completely Different Song'}),
                      video(snippet={'channelTitle': 'Another Artist', 'title': 'Golden Morning'}),
                      video(snippet={'title': 'Artist One - Golden Morning Live'}),
                      video(snippet={'title': 'Artist One - Golden Morning Karaoke'}),
                      video(snippet={'title': 'Artist One - Golden Morning Remix'}),
                      video(contentDetails={'duration': 'PT10M'})]
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertIsNone(_match_candidate(track(), candidate))
        self.assertIsNotNone(_match_candidate(track(track_name='Golden Morning - Live'),
            video(snippet={'title': 'Artist One - Golden Morning Live'})))

    def test_public_embed_region_age_and_live_restrictions_are_enforced(self):
        candidates = [video(status={'embeddable': False}), video(status={'privacyStatus': 'private'}),
                      video(contentDetails={'regionRestriction': {'blocked': ['KR']}}),
                      video(contentDetails={'regionRestriction': {'allowed': ['US']}}),
                      video(contentDetails={'regionRestriction': {'allowed': []}}),
                      video(contentDetails={'contentRating': {'ytRating': 'ytAgeRestricted'}}),
                      video(snippet={'liveBroadcastContent': 'upcoming'}),
                      video(snippet={'liveBroadcastContent': 'live'})]
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertIsNone(_match_candidate(track(), candidate))

    def test_cached_candidates_are_shared_by_source_identity_and_filtered_without_new_api_calls(self):
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=[
                self.search_payload(('abcdefghijk', 'lmnopqrstuv')), [video(), video('lmnopqrstuv')]]) as request:
            first = resolve_playback_candidates(track(), owner_id='one')
            second = resolve_playback_candidates(track(), ['abcdefghijk'], owner_id='two')
            exhausted = resolve_playback_candidates(track(), ['abcdefghijk', 'lmnopqrstuv'])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(first['candidates']), 2)
        self.assertEqual([item['video_id'] for item in second['candidates']], ['lmnopqrstuv'])
        self.assertEqual(exhausted['status'], 'NO_MATCH')

    def test_changed_source_metadata_uses_new_cache_identity(self):
        with patch('backend.recommendation.youtube_playback._api_json', return_value=[]) as request:
            resolve_playback_candidates(track())
            resolve_playback_candidates(track())
            resolve_playback_candidates(track(album_name='A Different Recording'))
        self.assertEqual(request.call_count, 2)

    def test_failed_verified_embed_uses_api_alternative_without_mutating_verified_mapping(self):
        original = self.mapped_track()
        before = deepcopy(original)
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=[self.search_payload(), [video()]]):
            result = resolve_playback_candidates(original, ['mapped12345'])
        self.assertEqual(original, before)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['candidates'][0]['video_id'], 'abcdefghijk')
        self.assertEqual(result['candidates'][0]['match_status'], 'CANDIDATE')

    def test_duplicate_ids_and_out_of_search_videos_are_not_returned(self):
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=[
                self.search_payload(('abcdefghijk', 'abcdefghijk')), [video(), video(), video('outside1234')]]) as request:
            result = resolve_playback_candidates(track())
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(request.call_args_list[1].args[1]['id'], 'abcdefghijk')

    def test_no_match_is_not_a_claim_that_no_video_exists_on_youtube(self):
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=[self.search_payload(),
                [video(status={'embeddable': False})]]):
            result = resolve_playback_candidates(track())
        self.assertEqual(result['status'], 'NO_MATCH')
        self.assertIn('검색한 후보', result['message'])

    def test_upstream_failure_is_short_cached_and_does_not_expose_secret(self):
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=SearchFailure('API_QUOTA_EXCEEDED')) as request:
            first = resolve_playback_candidates(track())
            second = resolve_playback_candidates(track())
        self.assertEqual(request.call_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(first['reason'], 'API_QUOTA_EXCEEDED')
        self.assertNotIn('test-key-no-network', json.dumps(first))

    @override_settings(YOUTUBE_SEARCH_PER_OWNER_MINUTE=1)
    def test_owner_rate_limit_blocks_new_search_but_allows_cached_or_verified_candidates(self):
        with patch('backend.recommendation.youtube_playback._api_json', return_value=[]) as request:
            first = resolve_playback_candidates(track(), owner_id='one')
            cached = resolve_playback_candidates(track(), owner_id='one')
            denied = resolve_playback_candidates(track(track_id='other'), owner_id='one')
            mapped = resolve_playback_candidates(self.mapped_track(), owner_id='one')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(first, cached)
        self.assertEqual(denied['reason'], 'API_RATE_LIMITED')
        self.assertEqual(mapped['status'], 'READY')

    @override_settings(YOUTUBE_SEARCH_DAILY_LIMIT=1)
    def test_daily_limit_bounds_all_owners(self):
        with patch('backend.recommendation.youtube_playback._api_json', return_value=[]) as request:
            resolve_playback_candidates(track(), owner_id='one')
            denied = resolve_playback_candidates(track(track_id='other'), owner_id='two')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(denied['reason'], 'API_DAILY_LIMIT')

    def test_concurrent_source_lookup_does_not_issue_duplicate_network_requests(self):
        def while_inflight(*args):
            second = resolve_playback_candidates(track(), owner_id='two')
            self.assertEqual(second['reason'], 'API_BUSY')
            return []
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=while_inflight) as request:
            first = resolve_playback_candidates(track(), owner_id='one')
        self.assertEqual(first['status'], 'NO_MATCH')
        self.assertEqual(request.call_count, 1)

    def test_http_errors_are_classified_without_echoing_server_error_or_api_key(self):
        for status, reason, expected in [(403, 'quotaExceeded', 'API_QUOTA_EXCEEDED'),
                                         (403, 'keyInvalid', 'API_AUTH_FAILED'),
                                         (429, 'userRateLimitExceeded', 'API_RATE_LIMITED'),
                                         (500, 'backendError', 'API_NETWORK_ERROR')]:
            error = HTTPError('https://example.com/?key=secret', status, 'secret', {},
                              BytesIO(json.dumps({'error': {'errors': [{'reason': reason}], 'message': 'secret'}}).encode()))
            opener = MagicMock()
            opener.open.side_effect = error
            with self.subTest(status=status), patch('backend.recommendation.youtube_playback.build_opener', return_value=opener):
                with self.assertRaises(SearchFailure) as failure:
                    _api_json('search', {}, 'secret')
            self.assertEqual(failure.exception.reason, expected)
            self.assertNotIn('secret', str(failure.exception))

    def test_network_and_invalid_upstream_payload_are_handled(self):
        opener = MagicMock()
        opener.open.side_effect = URLError('secret-in-url')
        with patch('backend.recommendation.youtube_playback.build_opener', return_value=opener):
            with self.assertRaises(SearchFailure) as failure:
                _api_json('search', {}, 'secret')
        self.assertEqual(failure.exception.reason, 'API_NETWORK_ERROR')
        opener.open.side_effect = None
        opener.open.return_value.__enter__.return_value.read.return_value = b'{"items":"wrong-shape"}'
        with patch('backend.recommendation.youtube_playback.build_opener', return_value=opener):
            with self.assertRaises(SearchFailure) as failure:
                _api_json('search', {}, 'secret')
        self.assertEqual(failure.exception.reason, 'API_INVALID_RESPONSE')
