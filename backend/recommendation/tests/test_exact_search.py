from fractions import Fraction
from time import monotonic
from unittest import TestCase

from backend.recommendation import solver
from backend.recommendation.policy import TARGET


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

\n