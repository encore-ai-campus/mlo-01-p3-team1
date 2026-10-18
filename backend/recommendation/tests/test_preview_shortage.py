from unittest import TestCase
from unittest.mock import patch

from ortools.sat.python import cp_model

from backend.recommendation.errors import DomainError
from backend.recommendation.policy import MAXIMUM, MINIMUM, TARGET
from backend.recommendation.solver import choose_preview


def candidate(key, duration=240000, genres=('JAZZ',)):
    return {'track_id':key,'duration_ms':duration,'genre_group_codes':list(genres),'scores':{'S':100}}


class PreviewShortageTests(TestCase):
    def failure(self, candidates, **options):
        with self.assertRaises(DomainError) as caught:
            choose_preview(candidates, **options)
        return caught.exception

    def test_complete_three_song_duration_proves_shortage_and_explains_time(self):
        failure=self.failure([candidate('a',240000),candidate('b',241000),candidate('c',277000)])
        self.assertEqual(failure.code,'CANDIDATE_SHORTAGE')
        self.assertEqual(failure.details['candidate_count'],3)
        self.assertEqual(failure.details['total_ms'],758000)
        self.assertEqual(failure.details['min_duration_ms'],MINIMUM)
        self.assertEqual(failure.details['target_duration_ms'],TARGET)
        self.assertEqual(failure.details['max_duration_ms'],MAXIMUM)
        self.assertIn('3곡',failure.message)
        self.assertIn('12분 38초',failure.message)
        self.assertEqual(failure.details['reason'],'TOTAL_DURATION_BELOW_MINIMUM')

    def test_missing_genre_has_korean_label_and_full_candidate_counts(self):
        failure=self.failure([candidate('a',6000000),candidate('b',6000000)],selected_genres=['JAZZ','BLUES'])
        self.assertEqual(failure.code,'CANDIDATE_SHORTAGE')
        self.assertEqual(failure.details['missing_genres'],['BLUES'])
        self.assertEqual(failure.details['missing_genre_labels'],['블루스'])
        self.assertEqual(failure.details['genre_candidate_counts'],{'JAZZ':2,'BLUES':0})
        self.assertIn('블루스',failure.message)

    def test_one_multigenre_song_cannot_represent_two_selected_genres(self):
        failure=self.failure([candidate('a',TARGET,['JAZZ','BLUES'])],selected_genres=['JAZZ','BLUES'])
        self.assertEqual(failure.code,'CANDIDATE_SHORTAGE')
        self.assertEqual(failure.details['missing_genres'],[])
        self.assertFalse(failure.details['distinct_genre_representatives_possible'])
        self.assertEqual(failure.details['reason'],'DISTINCT_GENRE_REPRESENTATIVES_UNAVAILABLE')

    def test_regeneration_uses_original_parent_count_for_proven_new_track_shortage(self):
        parent={f'old-{index}' for index in range(49)}
        rows=[candidate(f'old-{index}') for index in range(44)]+[candidate('new')]
        failure=self.failure(rows,parent_ids=parent)
        self.assertEqual(failure.code,'NO_MEANINGFUL_CHANGE')
        self.assertEqual(failure.details['parent_track_count'],49)
        self.assertEqual(failure.details['required_new_count'],9)
        self.assertEqual(failure.details['available_new_count'],1)
        self.assertIn('현재 선곡표는 유지됩니다',failure.message)

    def test_full_integer_combination_infeasible_is_proven_shortage(self):
        failure=self.failure([candidate('a',6000000),candidate('b',6000000)])
        self.assertEqual(failure.code,'CANDIDATE_SHORTAGE')
        self.assertEqual(failure.details['reason'],'FULL_ELIGIBLE_POOL_PROVEN_INFEASIBLE')
        self.assertEqual(failure.details['solver_windows'][-1]['solver_status'],'INFEASIBLE')

    def test_unknown_is_incomplete_even_when_no_greedy_solution_was_found(self):
        with patch('backend.recommendation.solver.cp_model.CpSolver.Solve',return_value=cp_model.UNKNOWN):
            failure=self.failure([candidate('a',6000000),candidate('b',6000000)])
        self.assertEqual(failure.code,'SEARCH_INCOMPLETE')
        self.assertEqual(failure.status,503)
        self.assertEqual(failure.details['solver_windows'][-1]['solver_status'],'UNKNOWN')

    def test_full_pool_larger_than_solver_limit_is_not_proven_by_smaller_windows(self):
        rows=[candidate(str(index),MAXIMUM+1) for index in range(801)]
        with patch('backend.recommendation.solver.cp_model.CpSolver.Solve',return_value=cp_model.INFEASIBLE):
            failure=self.failure(rows)
        self.assertEqual(failure.code,'SEARCH_INCOMPLETE')
        self.assertEqual([window['window_size'] for window in failure.details['solver_windows']],[200,400,800])

    def test_off_does_not_open_80_percent_after_unknown_in_100_percent_stage(self):
        rows=[candidate('a',6000000),candidate('b',6000000),candidate('other',100000,['POP'])]
        with patch('backend.recommendation.solver.cp_model.CpSolver.Solve',return_value=cp_model.UNKNOWN) as solve:
            failure=self.failure(rows,mode='OFF',selected_genres=['JAZZ'])
        self.assertEqual(failure.code,'SEARCH_INCOMPLETE')
        self.assertEqual(failure.details['genre_share_stage'],100)
        self.assertEqual(solve.call_count,1)

    def test_off_selected_genre_duration_must_be_able_to_reach_80_percent(self):
        failure=self.failure([candidate('jazz',60000),candidate('other',TARGET-60000,['POP'])],
                             mode='OFF',selected_genres=['JAZZ'])
        self.assertEqual(failure.code,'CANDIDATE_SHORTAGE')
        self.assertEqual(failure.details['selected_genre_total_ms'],60000)
        self.assertEqual(failure.details['required_selected_duration_ms'],4*MINIMUM//5)

    def test_off_can_open_80_percent_after_full_100_percent_duration_proof(self):
        rows=[candidate(f'jazz-{index}') for index in range(36)]+[candidate(f'pop-{index}',genres=['POP']) for index in range(9)]
        chosen,diagnostics=choose_preview(rows,mode='OFF',selected_genres=['JAZZ'])
        self.assertEqual(diagnostics['genre_share_stage'],80)
        total=sum(row['duration_ms'] for row in chosen)
        selected=sum(row['duration_ms'] for row in chosen if 'JAZZ' in row['genre_group_codes'])
        self.assertGreaterEqual(5*selected,4*total)

    def test_feasible_preview_keeps_original_valid_time(self):
        chosen,diagnostics=choose_preview([candidate(str(index)) for index in range(45)])
        self.assertTrue(MINIMUM<=sum(row['duration_ms'] for row in chosen)<=MAXIMUM)
        self.assertEqual(diagnostics['solver_status'],'FEASIBLE_GREEDY_PREVIEW')
