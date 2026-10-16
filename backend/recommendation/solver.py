"""Exact-duration playlist search with expanding candidate windows."""
from fractions import Fraction
from hashlib import sha256
from heapq import nsmallest
from math import lcm
from time import monotonic
from ortools.sat.python import cp_model
from .errors import DomainError, require
from .policy import MINIMUM, TARGET, MAXIMUM, GENRES


def representatives(tracks, genres):
    """Return a deterministic distinct-track assignment or None."""
    by_track={track['track_id']:set(track['genre_group_codes']) for track in tracks}
    assigned={}
    def augment(genre,seen):
        for track_id in by_track:
            if track_id in seen or genre not in by_track[track_id]: continue
            seen.add(track_id)
            if track_id not in assigned or augment(assigned[track_id],seen):
                assigned[track_id]=genre
                return True
        return False
    for genre in genres:
        if not augment(genre,set()): return None
    return {genre:track_id for track_id,genre in assigned.items()}


def _solve_window(candidates, deadline, selected_genres=(), min_selected_share=0, seed=''):
    def tie(track):
        key=sha256((seed+'\0'+track['track_id']).encode()).digest() if seed else b''
        return key,track['track_id']
    candidates = sorted(candidates, key=tie)
    if sum(t['duration_ms'] for t in candidates) < MINIMUM: return None
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
        if selected_genres:
            selected_duration = sum(x*t['duration_ms'] for x,t in zip(xs,candidates)
                                    if set(t['genre_group_codes']) & set(selected_genres))
            model.Add(100*selected_duration >= min_selected_share*total)
            representative = { (i,g):model.NewBoolVar(f'rep{i}_{g}')
                for i,t in enumerate(candidates) for g in selected_genres if g in t['genre_group_codes'] }
            for (i,g),var in representative.items(): model.Add(var <= xs[i])
            for g in selected_genres:
                model.Add(sum(v for (i,genre),v in representative.items() if genre==g) >= 1)
            for i in range(len(candidates)):
                model.Add(sum(v for (j,g),v in representative.items() if i==j) <= 1)
        model.Minimize(total if low >= TARGET else -total)
        solver, status = solve(model)
        if status == cp_model.INFEASIBLE: continue
        model.Add(total == solver.Value(total))
        weights = [Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in candidates]
        denominator = lcm(*(w.denominator for w in weights))
        coefficients = [int(w*denominator) for w in weights]
        require(sum(abs(c) for c in coefficients) < 2**62, 'SEARCH_INCOMPLETE', '정확한 점수 연산 범위를 초과했어요.', 503)
        quality = sum(x*c for x,c in zip(xs,coefficients))
        model.Maximize(quality)
        solver, _ = solve(model)
        model.Add(quality == solver.Value(quality))
        for x in xs:
            model.Maximize(x)
            solver, _ = solve(model)
            model.Add(x == solver.Value(x))
        return sorted([t for x,t in zip(xs,candidates) if solver.Value(x)],
                      key=lambda t:(-Fraction(t['scores']['S'] or 0),t['track_id']))
    return None


def choose(candidates, max_candidates, seconds, mode='ON', selected_genres=(), seed='', diagnostics=None):
    require(seconds > 0, 'POLICY_NOT_READY', '탐색 설정을 기다리고 있어요.', 503)
    limit = len(candidates) if max_candidates == 0 else min(len(candidates), max_candidates)
    require(limit > 0, 'CANDIDATE_SHORTAGE', '조건에 맞는 곡이 부족해요.', 422)
    def tie(track): return sha256((seed+'\0'+track['track_id']).encode()).digest() if mode=='OFF' and seed else b''
    ordered = sorted(candidates,key=lambda t:(-Fraction(t['scores']['S'] or 0),tie(t),t['track_id']))
    deadline = monotonic()+seconds
    stages=(100,80) if mode=='OFF' and selected_genres else (0,)
    for share in stages:
        stage_candidates=([t for t in ordered if set(t['genre_group_codes']) & set(selected_genres)]
                          if share==100 else ordered)
        if selected_genres and mode=='OFF':
            reps=representatives(stage_candidates,selected_genres)
            if reps is not None:
                front=set(reps.values())
                stage_candidates=[t for t in stage_candidates if t['track_id'] in front]+[
                    t for t in stage_candidates if t['track_id'] not in front]
        stage_limit=min(len(stage_candidates),limit)
        stage_sizes=[]
        if stage_limit:
            size=min(200,stage_limit)
            while True:
                stage_sizes.append(size)
                if size==stage_limit: break
                size=min(size*2,stage_limit)
        for size in stage_sizes:
            pool=stage_candidates[:size]
            result=_solve_window(pool,deadline,selected_genres,share,seed if mode=='OFF' else '')
            if result is not None:
                if diagnostics is not None:
                    selected_duration=sum(t['duration_ms'] for t in result
                                          if set(t['genre_group_codes']) & set(selected_genres)) if selected_genres else None
                    assigned=representatives(result,selected_genres) if selected_genres else {}
                    diagnostics.update({'solver_status':'OPTIMAL','candidate_count':len(candidates),
                                        'window_size':size,'genre_share_stage':share or None,
                                        'searched_full_pool':size==len(stage_candidates),
                                        'selected_duration_ms':selected_duration,
                                        'other_duration_ms':sum(t['duration_ms'] for t in result)-selected_duration if selected_genres else None,
                                        'genre_representatives':assigned})
                return result
        if stage_limit<len(stage_candidates):
            raise DomainError('SEARCH_INCOMPLETE','전체 적격 후보를 아직 탐색하지 못했어요.',503)
    raise DomainError('CANDIDATE_SHORTAGE','전체 적격 후보로 허용 시간의 선곡표를 구성할 수 없어요.',422)


def choose_preview(candidates, mode='ON', selected_genres=(), seed='', parent_ids=()):
    """Local, unreviewed CSV preview: feasible time/filters, without optimality claims."""
    parent_ids=set(parent_ids)
    required_new=max(1,len(parent_ids)//5) if parent_ids else 0
    total_ms=sum(t['duration_ms'] for t in candidates)
    available_new=len({t['track_id'] for t in candidates}-parent_ids)
    genre_counts={genre:sum(genre in t['genre_group_codes'] for t in candidates) for genre in selected_genres}
    missing_genres=[genre for genre,count in genre_counts.items() if not count]
    labels=lambda codes:[GENRES.get(code,(code,))[0] for code in codes]
    distinct_possible=not selected_genres or representatives(candidates,selected_genres) is not None
    details={'candidate_count':len(candidates),'total_ms':total_ms,'min_duration_ms':MINIMUM,
             'target_duration_ms':TARGET,'max_duration_ms':MAXIMUM,
             'selected_genre_codes':list(selected_genres),'genre_candidate_counts':genre_counts,
             'missing_genres':missing_genres,'missing_genre_labels':labels(missing_genres),
             'distinct_genre_representatives_possible':distinct_possible,
             'parent_track_count':len(parent_ids),'required_new_count':required_new,
             'available_new_count':available_new,'checked_full_candidate_pool':True}
    def fail(code,message,reason,**extra):
        raise DomainError(code,message,503 if code=='SEARCH_INCOMPLETE' else 422,
                          {**details,'reason':reason,**extra})
    if total_ms<MINIMUM:
        minutes,seconds=divmod(total_ms//1000,60)
        absent=(' 후보가 없는 장르: '+', '.join(labels(missing_genres))+'.') if missing_genres else ''
        fail('CANDIDATE_SHORTAGE',
             f'조건에 맞는 후보는 {len(candidates)}곡, 총 {minutes}분 {seconds:02d}초로 최소 {MINIMUM//60000}분보다 짧아요.'
             +absent+' 선택 조건을 확인해 주세요.','TOTAL_DURATION_BELOW_MINIMUM')
    if missing_genres:
        fail('CANDIDATE_SHORTAGE','선택한 장르의 후보가 없어요: '+', '.join(labels(missing_genres))
             +'. 선택 조건을 확인해 주세요.','SELECTED_GENRE_MISSING')
    if not distinct_possible:
        fail('CANDIDATE_SHORTAGE','선택한 장르('+', '.join(labels(selected_genres))
             +')를 서로 다른 곡으로 대표할 수 없어요. 선택 조건을 확인해 주세요.',
             'DISTINCT_GENRE_REPRESENTATIVES_UNAVAILABLE')
    if required_new and available_new<required_new:
        fail('NO_MEANINGFUL_CHANGE',
             f'필요한 신규 곡 수를 채우지 못했어요. 현재 조건의 신규 후보는 {available_new}곡이고 필요한 수는 {required_new}곡입니다. 현재 선곡표는 유지됩니다.',
             'AVAILABLE_NEW_TRACKS_BELOW_REQUIREMENT')
    if mode=='OFF' and selected_genres:
        selected_total=sum(t['duration_ms'] for t in candidates if set(t['genre_group_codes']) & set(selected_genres))
        minimum_selected=(4*MINIMUM+4)//5
        if selected_total<minimum_selected:
            fail('CANDIDATE_SHORTAGE','선택한 장르('+', '.join(labels(selected_genres))
                 +')의 후보 재생시간이 부족해 80% 장르 조건과 최소 176분을 함께 채울 수 없어요. 선택 조건을 확인해 주세요.',
                 'SELECTED_GENRE_DURATION_BELOW_REQUIRED_SHARE',selected_genre_total_ms=selected_total,
                 required_selected_duration_ms=minimum_selected)
    def greedy(pool, share):
        assigned=representatives(pool,selected_genres) if selected_genres else {}
        if assigned is None: return None
        required=set(assigned.values())
        first=[t for t in pool if t['track_id'] in required]
        fresh=[t for t in pool if t['track_id'] not in parent_ids and t['track_id'] not in required]
        fresh.sort(key=lambda t:(0 if set(t['genre_group_codes']) & set(selected_genres) else 1,
                                 t['duration_ms'],t['track_id']))
        first+=fresh[:max(0,required_new-sum(t['track_id'] not in parent_ids for t in first))]
        chosen_ids={t['track_id'] for t in first}
        rest=[t for t in pool if t['track_id'] not in chosen_ids]
        if share==80:
            rest.sort(key=lambda t:0 if set(t['genre_group_codes']) & set(selected_genres) else 1)
        chosen=[];total=0;selected_duration=0;new_count=0
        for track in first+rest:
            duration=track['duration_ms']
            if total+duration>MAXIMUM: continue
            chosen.append(track);total+=duration
            if track['track_id'] not in parent_ids: new_count+=1
            if set(track['genre_group_codes']) & set(selected_genres): selected_duration+=duration
            if total>=MINIMUM and new_count>=required_new and 100*selected_duration>=share*total: return chosen
        return None
    def tie(track): return sha256((seed+'\0'+track['track_id']).encode()).digest() if mode=='OFF' else b''
    def rank(track): return (-Fraction(track['scores']['S'] or 0),tie(track),track['track_id'])
    stages=(100,80) if mode=='OFF' and selected_genres else (0,)
    solver_windows=[]
    for share in stages:
        stage=[t for t in candidates if set(t['genre_group_codes']) & set(selected_genres)] if share==100 else candidates
        # Necessary conditions over the entire stage prove impossibility without
        # treating a limited window or failed greedy attempt as such a proof.
        if (not stage or sum(t['duration_ms'] for t in stage)<MINIMUM
                or len({t['track_id'] for t in stage}-parent_ids)<required_new): continue
        full_stage_infeasible=False
        for size in sorted({min(len(stage),n) for n in (200,400,800,len(stage))}):
            pool=sorted(stage,key=rank) if size==len(stage) else nsmallest(size,stage,key=rank)
            if sum(t['duration_ms'] for t in pool)<MINIMUM: continue
            if sum(t['track_id'] not in parent_ids for t in pool)<required_new: continue
            result=greedy(pool,share)
            if result is not None:
                return result,{'solver_status':'FEASIBLE_GREEDY_PREVIEW','window_size':len(pool),
                               'genre_share_stage':share or None,'candidate_count':len(candidates)}
            if size>800: continue
            model=cp_model.CpModel()
            xs=[model.NewBoolVar(f'p{i}') for i in range(len(pool))]
            total=sum(x*t['duration_ms'] for x,t in zip(xs,pool))
            model.Add(total>=MINIMUM);model.Add(total<=MAXIMUM)
            if required_new:
                model.Add(sum(x for x,t in zip(xs,pool) if t['track_id'] not in parent_ids)>=required_new)
            if selected_genres:
                selected_duration=sum(x*t['duration_ms'] for x,t in zip(xs,pool)
                                      if set(t['genre_group_codes']) & set(selected_genres))
                model.Add(100*selected_duration>=share*total)
                reps={(i,g):model.NewBoolVar(f'r{i}_{g}') for i,t in enumerate(pool)
                      for g in selected_genres if g in t['genre_group_codes']}
                for (i,g),rep in reps.items(): model.Add(rep<=xs[i])
                for g in selected_genres: model.Add(sum(v for (i,key),v in reps.items() if key==g)>=1)
                for i in range(len(pool)): model.Add(sum(v for (j,g),v in reps.items() if i==j)<=1)
            solver=cp_model.CpSolver()
            solver.parameters.max_time_in_seconds=5
            solver.parameters.num_search_workers=1
            solver.parameters.stop_after_first_solution=True
            status=solver.Solve(model)
            solver_windows.append({'window_size':len(pool),'genre_share_stage':share or None,
                                   'solver_status':{cp_model.UNKNOWN:'UNKNOWN',cp_model.MODEL_INVALID:'MODEL_INVALID',
                                                    cp_model.INFEASIBLE:'INFEASIBLE',cp_model.FEASIBLE:'FEASIBLE',
                                                    cp_model.OPTIMAL:'OPTIMAL'}.get(status,'UNRECOGNIZED')})
            if status in (cp_model.FEASIBLE,cp_model.OPTIMAL):
                result=[t for x,t in zip(xs,pool) if solver.Value(x)]
                return sorted(result,key=lambda t:(-Fraction(t['scores']['S'] or 0),t['track_id'])),{
                    'solver_status':'FEASIBLE_PREVIEW','window_size':len(pool),'genre_share_stage':share or None,
                    'candidate_count':len(candidates)}
            if len(pool)==len(stage) and status==cp_model.INFEASIBLE:
                full_stage_infeasible=True
                break
        if not full_stage_infeasible:
            fail('SEARCH_INCOMPLETE','정해진 탐색 범위나 시간 안에 선곡표 구성을 확인하지 못했어요. 현재 조건은 유지됩니다.',
                 'SOLVER_OR_FULL_POOL_SEARCH_INCOMPLETE',genre_share_stage=share or None,
                 solver_windows=solver_windows)
    fail('CANDIDATE_SHORTAGE','전체 적격 후보로 선택 조건과 176~184분을 함께 만족하는 선곡표를 구성할 수 없어요. 선택 조건을 확인해 주세요.',
         'FULL_ELIGIBLE_POOL_PROVEN_INFEASIBLE',solver_windows=solver_windows)
