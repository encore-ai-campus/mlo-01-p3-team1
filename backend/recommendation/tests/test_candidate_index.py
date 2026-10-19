from unittest import TestCase

from backend.recommendation.candidate_index import CandidateIndex, WEATHERS
from backend.recommendation.inputs import DEFAULTS, options as normalize_options
from backend.recommendation.policy import (
    GENRES, OFF_THEMES, SPEEDS,
    eligible, precompute_scores, score,
)


def track(index):
    genres = list(GENRES)
    return precompute_scores({
        'track_id': f'track-{index:03}',
        'track_name': f'곡 {index}',
        'artists_name': '가수',
        'album_name': '앨범',
        'duration_ms': 180_000 + (index % 11) * 17_000,
        'genre_group_codes': [genres[index % len(genres)]],
        'speed': sorted(SPEEDS)[index % len(SPEEDS)],
        'energy': index % 11,
        'raw_energy': f'{(index % 11) / 10:.1f}',
        'raw_acousticness': f'{((index * 3) % 11) / 10:.1f}',
        'raw_valence': f'{((index * 7) % 11) / 10:.1f}',
        'mode': bool(index % 2),
        'instrumental': index % 2 == 0,
        'instrumental_review_value': False if index == 0 else None,
        'occasion_status': 'GENERAL',
        'decision_source': 'RULE_SCREEN',
        'occasion_policy_version': 'test-policy',
        'occasion_decision_version': 'test-decision',
    })


def expected(rows, options, weather, allowed_genres, allowed_speeds, excluded):
    on = options['weather_influence_mode'] == 'ON'
    candidates = []
    audit = {'catalog_count': len(rows), 'common_eligible_count': 0, 'common_rejected_count': 0,
             'common_eligible_total_ms': 0, 'weather_rejected_count': 0,
             'off_missing_preference_count': 0}
    for row in rows:
        if not eligible(row, options, allowed_genres, allowed_speeds, excluded):
            audit['common_rejected_count'] += 1
            continue
        audit['common_eligible_count'] += 1
        audit['common_eligible_total_ms'] += row['duration_ms']
        values = score(row, options, weather)
        if values is None:
            audit['weather_rejected_count'] += 1
            continue
        if (not on and values['P'] is None and (options['selected_theme_codes']
                or options['selected_genre_codes'] or options['tempo_preference'] != 'auto')):
            audit['off_missing_preference_count'] += 1
            continue
        candidates.append(dict(row, scores=values))
    audit['candidate_count'] = len(candidates)
    audit['candidate_total_ms'] = sum(row['duration_ms'] for row in candidates)
    return candidates, audit


class CandidateIndexTests(TestCase):
    def test_index_matches_policy_and_audit_for_inherited_filters(self):
        rows = [track(index) for index in range(48)]
        rows[1]['score_cache']['weather_version'] = 'OLD'
        rows[2]['score_cache']['weather'].pop('RAIN')
        rows[3]['score_cache'] = {}
        rows[4]['instrumental_review_value'] = True
        rows[5]['score_cache']['weather']['RAIN'] = None
        index = CandidateIndex(rows)
        excluded = {'track-007', 'missing-id'}

        for mode in ('ON', 'OFF'):
            for weather in WEATHERS:
                for vocal in ('any', 'instrumental_only'):
                    options = {
                        **DEFAULTS,
                        'weather_influence_mode': mode,
                        'selected_theme_codes': ['CALM', 'BRIGHT'],
                        'selected_genre_codes': ['JAZZ'],
                        'tempo_preference': 'slow',
                        'vocal_option': vocal,
                    }
                    # These inherited family filters intentionally differ from UI options.
                    allowed_genres = ['JAZZ', 'POP']
                    allowed_speeds = ['slow', 'medium']
                    expected_rows, expected_audit = expected(
                        rows, options, weather, allowed_genres, allowed_speeds, excluded)
                    actual_rows, actual_audit = index.candidates(
                        options, weather, allowed_genres, allowed_speeds, excluded)
                    self.assertEqual(
                        [(row['track_id'], row['scores']) for row in actual_rows],
                        [(row['track_id'], row['scores']) for row in expected_rows],
                        (mode, weather, vocal),
                    )
                    self.assertEqual(actual_audit, expected_audit, (mode, weather, vocal))

    def test_all_selected_tags_and_no_preference_keep_candidate_contract(self):
        rows = [track(index) for index in range(36)]
        index = CandidateIndex(rows)
        all_tags = normalize_options({**DEFAULTS, 'weather_influence_mode': 'OFF',
                                      'selected_theme_codes': list(OFF_THEMES),
                                      'selected_genre_codes': list(GENRES), 'tempo_preference': 'auto'})
        off_defaults = {**DEFAULTS, 'weather_influence_mode': 'OFF'}
        self.assertEqual(all_tags, off_defaults)
        baseline, baseline_audit = expected(rows, off_defaults, None, [], [], set())
        actual, actual_audit = index.candidates(off_defaults, None, [], [], set())
        self.assertEqual([(row['track_id'], row['scores']) for row in actual],
                         [(row['track_id'], row['scores']) for row in baseline])
        self.assertEqual(actual_audit, baseline_audit)

    def test_masks_preserve_reviewed_instrumental_precedence(self):
        rows = [track(0), track(1)]
        rows[0]['instrumental'] = True
        rows[0]['instrumental_review_value'] = False
        rows[1]['instrumental'] = False
        rows[1]['instrumental_review_value'] = True
        options = {**DEFAULTS, 'weather_influence_mode': 'OFF', 'vocal_option': 'instrumental_only'}
        actual, audit = CandidateIndex(rows).candidates(options, None, [], [], set())
        self.assertEqual([row['track_id'] for row in actual], ['track-001'])
        self.assertEqual(audit['common_eligible_count'], 1)
