from fractions import Fraction
from math import lcm
from time import monotonic
from ortools.sat.python import cp_model
from .errors import DomainError, require
from .policy import MINIMUM, TARGET, MAXIMUM


def choose(candidates, max_candidates, seconds):
    require(max_candidates > 0 and seconds > 0, 'POLICY_NOT_READY', '탐색 설정을 기다리고 있어요.', 503)
    require(len(candidates) <= max_candidates, 'SEARCH_INCOMPLETE', '전체 후보를 탐색할 설정이 필요해요.', 503,
            eligible_count=len(candidates), candidate_limit=max_candidates)
    candidates = sorted(candidates, key=lambda t: t['track_id'])
    require(sum(t['duration_ms'] for t in candidates) >= MINIMUM, 'CANDIDATE_SHORTAGE', '조건에 맞는 곡이 부족해요.', 422)
    deadline = monotonic() + seconds
    def solve(model):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.001, deadline-monotonic())
        solver.parameters.num_search_workers = 1
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.INFEASIBLE):
            raise DomainError('SEARCH_INCOMPLETE', '정해진 시간 안에 탐색을 완료하지 못했어요.', 503)
        return solver, status
    for low, high in [(TARGET,TARGET), (TARGET+1,MAXIMUM), (MINIMUM,TARGET-1)]:
        model = cp_model.CpModel()
        xs = [model.NewBoolVar(f't{i}') for i in range(len(candidates))]
        total = sum(x*t['duration_ms'] for x,t in zip(xs,candidates))
        model.Add(total >= low); model.Add(total <= high)
        model.Minimize(total if low >= TARGET else -total)
        solver, status = solve(model)
        if status == cp_model.INFEASIBLE: continue
        model.Add(total == solver.Value(total))
        weights = [Fraction(t['scores']['S'])*t['duration_ms'] for t in candidates]
        denominator = lcm(*(w.denominator for w in weights))
        coefficients = [int(w*denominator) for w in weights]
        require(sum(abs(c) for c in coefficients) < 2**62, 'SEARCH_INCOMPLETE', '정확한 점수 연산 범위를 초과했어요.', 503)
        quality = sum(x*c for x,c in zip(xs,coefficients))
        model.Maximize(quality)
        solver, _ = solve(model)
        model.Add(quality == solver.Value(quality))
        # At fixed positive duration, a set cannot be a proper prefix of another.
        # Prefer inclusion of the smallest remaining ID to obtain the canonical set.
        for x in xs:
            model.Maximize(x)
            solver, _ = solve(model)
            model.Add(x == solver.Value(x))
        return sorted([t for x,t in zip(xs,candidates) if solver.Value(x)], key=lambda t:(-t['scores']['S'],t['track_id']))
    raise DomainError('CANDIDATE_SHORTAGE', '전체 적격 후보로 허용 시간의 선곡표를 구성할 수 없어요.')
