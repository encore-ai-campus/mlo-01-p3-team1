from fractions import Fraction
from hashlib import sha256
from itertools import product
from time import monotonic
from unittest import TestCase

from backend.recommendation import solver
from backend.recommendation.policy import TARGET, MINIMUM, MAXIMUM


def pool(jazz_count, pop_count, *, dual_count=0, equal_scores=False):
    tracks = []
    for index in range(jazz_count + pop_count + dual_count):
        if index < jazz_count:
            genres = ['JAZZ']
        elif index < jazz_count + pop_count:
            genres = ['POP']
        else:
            genres = ['JAZZ', 'POP']
        score = Fraction(80) if equal_scores else Fraction(60 + (index * 17) % 39, 1)
        tracks.append({'track_id': f'track-{index:02}', 'duration_ms': 900_000,
                       'genre_group_codes': genres, 'scores': {'S': score}})
    return tracks


class ExactSearchTests(TestCase):
    def assert_matches_exhaustive_search(self, candidates, genres, share, seed):
        ordered = sorted(candidates, key=lambda row: (
            sha256((seed + '\0' + row['track_id']).encode()).digest() if seed else b'',
            row['track_id']))
        best = None
        expected_ids = None
        for bits in product((0, 1), repeat=len(ordered)):
            chosen = [row for row, included in zip(ordered, bits) if included]
            total = sum(row['duration_ms'] for row in chosen)
            if not MINIMUM <= total <= MAXIMUM:
                continue
            selected_ms = sum(row['duration_ms'] for row in chosen
                              if set(genres).intersection(row['genre_group_codes']))
            if 100 * selected_ms < share * total:
                continue
            assignments = [[i for i, row in enumerate(chosen) if genre in row['genre_group_codes']]
                           for genre in genres]
            if not any(len(set(indices)) == len(genres) for indices in product(*assignments)):
                continue
            duration_rank = ((0, 0) if total == TARGET else
                             (1, total) if total > TARGET else (2, -total))
            quality = sum(row['scores']['S'] * row['duration_ms'] for row in chosen)
            rank = (duration_rank, -quality, tuple(-bit for bit in bits))
            if best is None or rank < best:
                best = rank
                expected_ids = {row['track_id'] for row in chosen}
        for search in (solver._solve_window, solver._solve_window_fallback):
            result = search(candidates, monotonic() + 5, genres, share, seed)
            self.assertEqual(None if result is None else {row['track_id'] for row in result},
                             expected_ids, search.__name__)

    def assert_same_solution(self, candidates, genres, share, seed='fixed-seed'):
        optimized = solver._solve_window(candidates, monotonic() + 5, genres, share, seed)
        fallback = solver._solve_window_fallback(candidates, monotonic() + 5, genres, share, seed)
        signature = lambda rows: [(row['track_id'], row['duration_ms'], row['scores']['S']) for row in rows]
        self.assertEqual(signature(optimized), signature(fallback))
        if optimized is not None:
            total = sum(row['duration_ms'] for row in optimized)
            self.assertTrue(10_560_000 <= total <= 11_040_000)
            if genres:
                selected = sum(row['duration_ms'] for row in optimized
                               if set(row['genre_group_codes']) & set(genres))
                self.assertGreaterEqual(100 * selected, share * total)

    def test_single_genre_share_uses_same_exact_solution_as_cp_sat_fallback(self):
        self.assert_same_solution(pool(11, 6), ['JAZZ'], 80)

    def test_two_genres_keep_distinct_representatives_and_full_share(self):
        self.assert_same_solution(pool(8, 8, dual_count=2), ['JAZZ', 'POP'], 100)

    def test_equal_score_genre_pool_keeps_deterministic_seed_ties(self):
        candidates = pool(8, 8, dual_count=1, equal_scores=True)
        self.assert_same_solution(candidates, ['JAZZ', 'POP'], 100)
        first = solver._solve_window(candidates, monotonic() + 5, ['JAZZ', 'POP'], 100, 'fixed-seed')
        second = solver._solve_window(candidates, monotonic() + 5, ['JAZZ', 'POP'], 100, 'fixed-seed')
        self.assertEqual([row['track_id'] for row in first], [row['track_id'] for row in second])

    def test_variable_durations_and_fractional_quality_match_exhaustive_optimum(self):
        candidates = pool(5, 5, dual_count=2)
        for index, row in enumerate(candidates):
            row['duration_ms'] = (21 + (index * 7) % 16) * 60_000
            row['scores']['S'] = Fraction(700 + (index * 13) % 107, 9)
        for genres, share in ((['JAZZ'], 80), (['JAZZ', 'POP'], 100)):
            for seed in ('', 'different-seed'):
                with self.subTest(genres=genres, seed=seed):
                    self.assert_matches_exhaustive_search(candidates, genres, share, seed)

    def test_nearest_duration_and_infeasible_pool_match_exhaustive_search(self):
        for duration_ms in (1_830_000, 1_770_000, 1_860_000):
            candidates = pool(4, 4)
            for row in candidates:
                row['duration_ms'] = duration_ms
            with self.subTest(duration_ms=duration_ms):
                self.assert_matches_exhaustive_search(candidates, ['JAZZ', 'POP'], 100, 'duration-seed')
