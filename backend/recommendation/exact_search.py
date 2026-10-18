"""Exact duration/quality/tie search with bounded, request-local state.

Ported from verified experiment 62587775dad7. No runtime source rewriting,
benchmark imports, global solver replacement, or file writes occur here.
Every shortcut certifies its result or retains the original fallback/deadline.
"""
from fractions import Fraction
from functools import lru_cache
import hashlib
from itertools import combinations, product
from collections import Counter
from math import gcd, isqrt, lcm
from time import monotonic
from ortools.sat.python import cp_model
from . import policy
from .errors import DomainError
from .matching import representatives



def _finish_reduced_cp(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats):
    """Solve only variables that the exact upper/lower bounds cannot fix."""
    costs = [abs(scores[i] - pivot) * candidates[i]['duration_ms'] for i in free]
    denominator = lcm(*(c.denominator for c in costs))
    coefficients = [int(c * denominator) for c in costs]
    common = gcd(*coefficients) or 1
    coefficients = [c // common for c in coefficients]
    if sum(coefficients) >= 2 ** 61:
        return None
    model = cp_model.CpModel()
    xs = [model.NewBoolVar(f'core{i}') for i in free]
    residual = target - sum((candidates[i]['duration_ms'] for i in forced_in))
    model.Add(sum((x * candidates[i]['duration_ms'] for x, i in zip(xs, free))) == residual)
    loss = sum(((1 - x if scores[i] > pivot else x) * c for x, i, c in zip(xs, free, coefficients)))
    model.Add(loss <= int((upper - lower) * denominator // common))
    values = [int(candidates[i]['track_id'] in hint) for i in free]

    def run(phase):
        model.ClearHints()
        for x, value in zip(xs, values):
            model.AddHint(x, value)
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.max_time_in_seconds = max(0.001, deadline - monotonic())
        status = solver.Solve(model)
        stats['last_status'] = solver.StatusName(status)
        stats['cp_calls'] = stats.get('cp_calls', 0) + 1
        if status != cp_model.OPTIMAL:
            return None
        values[:] = [solver.Value(x) for x in xs]
        return solver
    if stats.get('quality_probe_optimum'):
        model.Add(loss == int((upper - lower) * denominator // common))
    model.Minimize(loss)
    solver = run('core_quality')
    if solver is None:
        return None
    best_loss = solver.Value(loss)
    model.Add(loss == best_loss)
    for x, i, cost in zip(xs, free, coefficients):
        if cost > best_loss:
            model.Add(x == int(scores[i] > pivot))
    known = {candidates[i]['track_id'] for value, i in zip(values, free) if value}
    known.update((candidates[i]['track_id'] for i in forced_in))
    face = finish_optimal_face(candidates, scores, pivot, upper, Fraction(best_loss * common, denominator), forced_in, free, known, target, deadline, stats)
    if face is not None:
        return face
    for start in range(0, len(xs), 30):
        chunk = xs[start:start + 30]
        model.Maximize(sum((x * (1 << len(chunk) - 1 - j) for j, x in enumerate(chunk))))
        solver = run('core_tie')
        if solver is None:
            return None
        for x in chunk:
            model.Add(x == solver.Value(x))
    result = [candidates[i] for i in forced_in] + [candidates[i] for value, i in zip(values, free) if value]
    stats['method'] = 'reduced_cp'
    return result


def solve_core(candidates, target, deadline, stats=None, max_free=44):
    """Certify the exact unconstrained optimum at TARGET, or return None.

    The caller validates genre representatives/share before accepting the result.
    Sorting candidates by tie key before calling preserves original lex ordering.
    """
    stats = stats if stats is not None else {}
    scores = [Fraction(t['scores']['S'] or 0) for t in candidates]
    if not candidates or len(set(scores)) <= 1:
        return None
    weights = [score * t['duration_ms'] for score, t in zip(scores, candidates)]
    denominator = lcm(*(w.denominator for w in weights))
    coefficients = [int(w * denominator) for w in weights]
    if sum((abs(c) for c in coefficients)) >= 2 ** 62:
        return None
    by_id = {t['track_id']: index for index, t in enumerate(candidates)}
    ranked = sorted(range(len(candidates)), key=lambda i: (-scores[i], i))
    total = 0
    for cutoff, index in enumerate(ranked):
        if total + candidates[index]['duration_ms'] >= target:
            pivot = scores[index]
            break
        total += candidates[index]['duration_ms']
    else:
        return None
    upper = pivot * target + sum((max(Fraction(0), (score - pivot) * track['duration_ms']) for score, track in zip(scores, candidates)))
    best = None
    for width in (24, 28, 32, 36, 40, 44):
        start = max(0, cutoff - width // 2)
        end = min(len(ranked), start + width)
        prefix = ranked[:start]
        core_indices = sorted(ranked[start:end])
        prefix_total = sum((candidates[i]['duration_ms'] for i in prefix))
        result = numpy_subset([candidates[i] for i in core_indices], [coefficients[i] for i in core_indices], target - prefix_total, deadline, 44)
        if result is None:
            continue
        core_chosen, core_quality = result
        chosen = [candidates[i] for i in prefix] + core_chosen
        quality = Fraction(sum((coefficients[i] for i in prefix)) + core_quality, denominator)
        if best is None or quality > best[0]:
            best = (quality, chosen)
        if width == 44:
            extra = exchange_witness(candidates, target, pivot, upper, best[1], min(deadline, monotonic() + 1.5), stats)
            if extra is not None:
                extra_quality = sum((Fraction(t['scores']['S'] or 0) * t['duration_ms'] for t in extra))
                if extra_quality > best[0]:
                    best = (extra_quality, extra)
        lower = best[0]
        gap = upper - lower
        assert gap >= 0
        forced_in = []
        forced_out = []
        free = []
        for i, (score, track) in enumerate(zip(scores, candidates)):
            cost = abs(score - pivot) * track['duration_ms']
            if cost > gap:
                (forced_in if score > pivot else forced_out).append(i)
            else:
                free.append(i)
        stats.update({'initial_width': width, 'upper': str(upper), 'lower': str(lower), 'gap': str(gap), 'forced_in': len(forced_in), 'forced_out': len(forced_out), 'free': len(free), 'pivot_score': str(pivot)})
        if width in (36, 40) and len(free) > max_free:
            early = early_reduced_exact(candidates, scores, pivot, upper, lower, forced_in, free, {t['track_id'] for t in best[1]}, target, deadline, stats)
            if early is not None:
                stats['early_bound_width'] = width
                stats.update({'quality': str(sum((Fraction(t['scores']['S'] or 0) * t['duration_ms'] for t in early))), 'certified': True})
                return sorted(early, key=lambda t: (-Fraction(t['scores']['S'] or 0), t['track_id']))
        if len(free) > max_free:
            if width == 44:
                hint = {t['track_id'] for t in best[1]}
                chosen = finish_reduced_cp(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
                if chosen is not None:
                    final_quality = sum((Fraction(t['scores']['S'] or 0) * t['duration_ms'] for t in chosen))
                    assert sum((t['duration_ms'] for t in chosen)) == target and final_quality >= lower
                    stats.update({'quality': str(final_quality), 'certified': True, 'method': stats.get('method', 'array_exact')})
                    return sorted(chosen, key=lambda t: (-Fraction(t['scores']['S'] or 0), t['track_id']))
            continue
        residual = target - sum((candidates[i]['duration_ms'] for i in forced_in))
        exact = numpy_subset([candidates[i] for i in free], [coefficients[i] for i in free], residual, deadline, max_free)
        assert exact is not None, stats
        tracks, quality = exact
        chosen = [candidates[i] for i in forced_in] + tracks
        assert sum((t['duration_ms'] for t in chosen)) == target
        final_quality = Fraction(sum((coefficients[i] for i in forced_in)) + quality, denominator)
        assert final_quality >= lower
        stats.update({'quality': str(final_quality), 'certified': True, 'method': stats.get('method', 'array_exact')})
        return sorted(chosen, key=lambda t: (-Fraction(t['scores']['S'] or 0), t['track_id']))
    stats['certified'] = False
    return None


def exact_bits(tracks,target,deadline,stats=None):
    """Exact subset at one duration, original lex order, O(sqrt(n)*target) bits.

    Returns (handled, result); a handled None proves no subset at this target.
    """
    if target<0:return True,None
    if target==0:return True,[]
    if not tracks or sum(t['duration_ms'] for t in tracks)<target:return True,None
    unit=gcd(*(t['duration_ms'] for t in tracks))
    if target%unit:return True,None
    target//=unit
    count=len(tracks)
    block=max(1,isqrt(count))
    estimated=(count//block+block+4)*(target+1)//8
    if estimated>192*1024*1024:return False,None
    mask=(1<<(target+1))-1
    suffix={count:1}
    reachable=1
    threshold=target+1
    durations=[t['duration_ms']//unit for t in tracks]
    for i in range(count-1,-1,-1):
        if monotonic()>=deadline:raise TimeoutError('bitset deadline')
        d=durations[i]
        # Every sum >= threshold already exists; adding d >= threshold
        # cannot introduce any new sum, even when smaller holes remain.
        if d<threshold:
            reachable=(reachable|(reachable<<d))&mask
            threshold=(mask^reachable).bit_length()
        if i%block==0:suffix[i]=reachable
    if not (reachable>>target)&1:return True,None
    chosen=[]
    remaining=target
    for start in range(0,count,block):
        stop=min(start+block,count)
        local=[0]*(stop-start+1)
        local[-1]=suffix[stop]
        threshold=(mask^local[-1]).bit_length()
        for i in range(stop-1,start-1,-1):
            d=durations[i]
            reachable=local[i-start+1]
            if d<threshold:
                reachable=(reachable|(reachable<<d))&mask
                threshold=(mask^reachable).bit_length()
            local[i-start]=reachable
        for i in range(start,stop):
            if monotonic()>=deadline:raise TimeoutError('bitset reconstruction deadline')
            d=durations[i]
            if d<=remaining and (local[i-start+1]>>(remaining-d))&1:
                chosen.append(tracks[i]);remaining-=d
    assert remaining==0
    if stats is not None:stats.update({'bitset_tracks':count,'bitset_bytes_bound':estimated,'bitset_unit':unit})
    return True,chosen


def pivot_fill(ordered,target,deadline,stats):
    """Saturating the fractional bound proves global exact quality."""
    ranked=sorted(ordered,key=lambda t:-Fraction(t['scores']['S'] or 0))
    total=0
    for track in ranked:
        if total+track['duration_ms']>=target:
            pivot=Fraction(track['scores']['S'] or 0);break
        total+=track['duration_ms']
    else:return None
    above=[t for t in ordered if Fraction(t['scores']['S'] or 0)>pivot]
    equal=[t for t in ordered if Fraction(t['scores']['S'] or 0)==pivot]
    residual=target-sum(t['duration_ms'] for t in above)
    handled,chosen=exact_bits(equal,residual,deadline,stats)
    if chosen is None:return None
    result=above+chosen
    assert sum(t['duration_ms'] for t in result)==target
    upper=pivot*target+sum((Fraction(t['scores']['S'] or 0)-pivot)*t['duration_ms'] for t in above)
    assert sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in result)==upper
    stats.update({'method':'pivot_bitset','certified':True,'quality':str(upper),'pivot_score':str(pivot)})
    return sorted(result,key=lambda t:(-Fraction(t['scores']['S'] or 0),t['track_id']))


def exchange_witness(ordered,target,pivot,upper,current,deadline,stats):
    """At most 3 additions/removals improve a lower bound, never prove optimality."""
    count=len(ordered)
    losses=[abs(Fraction(t['scores']['S'] or 0)-pivot)*t['duration_ms'] for t in ordered]
    denominator=lcm(*(value.denominator for value in losses))
    costs=[int(value*denominator) for value in losses]
    bound=int((upper-sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in current))*denominator)
    baseline={i for i,t in enumerate(ordered) if Fraction(t['scores']['S'] or 0)>=pivot}
    base_mask=sum(1<<(count-1-i) for i in baseline)
    delta=target-sum(ordered[i]['duration_ms'] for i in baseline)
    remove=[(t['duration_ms'],costs[i],1<<(count-1-i)) for i,t in enumerate(ordered) if i in baseline and costs[i]<=bound]
    add=[(t['duration_ms'],costs[i],1<<(count-1-i)) for i,t in enumerate(ordered) if i not in baseline and costs[i]<=bound]
    def tuples(items):
        yield 0,0,0
        yield from items
        for a,b_ in combinations(items,2):yield a[0]+b_[0],a[1]+b_[1],a[2]+b_[2]
        for a,b_,c_ in combinations(items,3):yield a[0]+b_[0]+c_[0],a[1]+b_[1]+c_[1],a[2]+b_[2]+c_[2]
    removals={}
    work=0
    for duration,cost,mask in tuples(remove):
        work+=1
        if work%4096==0 and monotonic()>=deadline:return None
        if cost>bound:continue
        value=(cost,mask)
        if duration not in removals or value<removals[duration]:removals[duration]=value
    best=None
    for duration,cost,mask in tuples(add):
        work+=1
        if work%4096==0 and monotonic()>=deadline:break
        if cost>bound:continue
        removed=removals.get(duration-delta)
        if removed is None or removed[0]+cost>bound:continue
        full_mask=base_mask-removed[1]+mask
        key=(removed[0]+cost,-full_mask)
        if best is None or key<best:best=key;bound=key[0]
    stats['exchange_work']=work
    stats['exchange_removed_states']=len(removals)
    if best is None:return None
    mask=-best[1]
    chosen=[t for i,t in enumerate(ordered) if mask>>(count-1-i)&1]
    assert sum(t['duration_ms'] for t in chosen)==target
    quality=sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in chosen)
    assert (upper-quality)*denominator==best[0]
    stats['exchange_gap']=str(upper-quality)
    return chosen


def numpy_subset(tracks,coefficients,target,deadline,max_free=44):
    """Exact two-half search using bounded integer arrays, including lex ties."""
    import numpy as np
    count=len(tracks)
    if target<0 or count>min(max_free,44):return None
    if count==0:return ([],0) if target==0 else None
    if monotonic()>=deadline:raise TimeoutError('array subset deadline')
    split=count//2
    def arrays(items,values):
        size=1<<len(items)
        durations=np.empty(size,dtype=np.int64)
        qualities=np.empty(size,dtype=np.int64)
        durations[0]=0;qualities[0]=0
        length=1
        for track,value in reversed(list(zip(items,values))):
            durations[length:length*2]=durations[:length]+track['duration_ms']
            qualities[length:length*2]=qualities[:length]+value
            length*=2
        bits=np.arange(size,dtype=np.int64)
        valid=durations<=target
        return durations[valid],qualities[valid],bits[valid]
    left_d,left_q,left_bits=arrays(tracks[:split],coefficients[:split])
    # Last row for one duration has highest quality, then highest lex bits.
    order=np.lexsort((left_bits,left_q,left_d))
    left_d=left_d[order];left_q=left_q[order];left_bits=left_bits[order]
    last=np.empty(len(left_d),dtype=bool)
    last[-1]=True;last[:-1]=left_d[:-1]!=left_d[1:]
    left_d=left_d[last];left_q=left_q[last];left_bits=left_bits[last]
    del order,last
    if monotonic()>=deadline:raise TimeoutError('array subset sort deadline')
    right_d,right_q,right_bits=arrays(tracks[split:],coefficients[split:])
    wanted=target-right_d
    matches=np.searchsorted(left_d,wanted)
    valid=matches<len(left_d)
    indices=np.flatnonzero(valid)
    indices=indices[left_d[matches[indices]]==wanted[indices]]
    if not len(indices):return None
    qualities=left_q[matches[indices]]+right_q[indices]
    best_quality=int(qualities.max())
    indices=indices[qualities==best_quality]
    bits=(left_bits[matches[indices]]<<(count-split))|right_bits[indices]
    best_bits=int(bits.max())
    if monotonic()>=deadline:raise TimeoutError('array subset match deadline')
    return [t for i,t in enumerate(tracks) if best_bits>>(count-1-i)&1],best_quality


class SumOracle:
    """One bounded bitset answers many duration queries without copying big ints."""
    def __init__(self,tracks,maximum,deadline):
        self.tracks=tracks;self.deadline=deadline
        self.unit=gcd(*(t['duration_ms'] for t in tracks))
        self.upper=min(maximum,sum(t['duration_ms'] for t in tracks))//self.unit
        count=len(tracks);self.block=max(1,isqrt(count))
        self.bytes_bound=(count//self.block+self.block+5)*(self.upper+1)//8
        if self.bytes_bound>192*1024*1024:raise OverflowError('oracle memory gate')
        self.mask=(1<<(self.upper+1))-1
        self.durations=[t['duration_ms']//self.unit for t in tracks]
        self.suffix={count:1}
        value=1
        threshold=self.upper+1
        for i in range(count-1,-1,-1):
            if monotonic()>=deadline:raise TimeoutError('oracle build deadline')
            d=self.durations[i]
            if d<threshold:
                value=(value|(value<<d))&self.mask
                threshold=(self.mask^value).bit_length()
            if i%self.block==0:self.suffix[i]=value
        self.bits=value.to_bytes((self.upper+8)//8,'little')
        self.cache={}
        self.local_start=None;self.local=None;self.byte_index=None;self.byte_value=None
    def possible(self,target):
        if target<0 or target%self.unit:return False
        target//=self.unit
        return target<=self.upper and (self.bits[target//8]>>(target%8))&1
    def subset(self,target):
        if not self.possible(target):return None
        if target in self.cache:return self.cache[target]
        remaining=target//self.unit;chosen=[];count=len(self.tracks)
        for start in range(0,count,self.block):
            stop=min(start+self.block,count)
            local=[0]*(stop-start+1);local[-1]=self.suffix[stop]
            threshold=(self.mask^local[-1]).bit_length()
            for i in range(stop-1,start-1,-1):
                value=local[i-start+1];d=self.durations[i]
                if d<threshold:
                    value=(value|(value<<d))&self.mask
                    threshold=(self.mask^value).bit_length()
                local[i-start]=value
            for i in range(start,stop):
                if monotonic()>=self.deadline:raise TimeoutError('oracle lex deadline')
                d=self.durations[i]
                if d<=remaining and (local[i-start+1]>>(remaining-d))&1:
                    chosen.append(self.tracks[i]);remaining-=d
        assert remaining==0
        self.cache[target]=chosen
        return chosen

    def suffix_at(self,index):
        count=len(self.tracks)
        if index==count:return 1
        start=(index//self.block)*self.block
        if self.local_start!=start:
            stop=min(start+self.block,count)
            local=[0]*(stop-start+1);local[-1]=self.suffix[stop]
            threshold=(self.mask^local[-1]).bit_length()
            for i in range(stop-1,start-1,-1):
                value=local[i-start+1];d=self.durations[i]
                if d<threshold:
                    value=(value|(value<<d))&self.mask
                    threshold=(self.mask^value).bit_length()
                local[i-start]=value
            self.local_start=start;self.local=local
        return self.local[index-start]
    def possible_from(self,index,target):
        if target<0 or target%self.unit:return False
        target//=self.unit
        if target>self.upper:return False
        if self.byte_index!=index:
            value=self.suffix_at(index)
            self.byte_value=value.to_bytes((self.upper+8)//8,'little')
            self.byte_index=index
        return (self.byte_value[target//8]>>(target%8))&1
    def subset_from(self,index,target):
        if not self.possible_from(index,target):return None
        remaining=target//self.unit;chosen=[]
        for i in range(index,len(self.tracks)):
            if monotonic()>=self.deadline:raise TimeoutError('suffix reconstruction deadline')
            d=self.durations[i]
            if d<=remaining and (self.suffix_at(i+1)>>(remaining-d))&1:
                chosen.append(self.tracks[i]);remaining-=d
            if remaining==0:break
        assert remaining==0
        return chosen


class CountSumOracle:
    """Suffix sums with at least k tracks from one Hall-deficient genre set."""
    def __init__(self,tracks,maximum,deadline,groups,needed):
        self.tracks=tracks;self.deadline=deadline;self.groups=set(groups);self.needed=needed
        self.unit=gcd(*(t['duration_ms'] for t in tracks))
        self.upper=min(maximum,sum(t['duration_ms'] for t in tracks))//self.unit
        count=len(tracks);self.block=max(1,isqrt(count))
        self.bytes_bound=(count//self.block+self.block+5)*(self.upper+1)*(needed+1)//8
        if self.bytes_bound>384*1024*1024:raise OverflowError('count oracle memory gate')
        self.mask=(1<<(self.upper+1))-1
        self.durations=[t['duration_ms']//self.unit for t in tracks]
        self.marked=[int(bool(self.groups.intersection(t['genre_group_codes']))) for t in tracks]
        value=(1,)+(0,)*needed;self.suffix={count:value}
        thresholds=[self.upper+1]*(needed+1)
        for i in range(count-1,-1,-1):
            if monotonic()>=deadline:raise TimeoutError('count oracle build deadline')
            value=self.add(value,i,thresholds)
            if i%self.block==0:self.suffix[i]=value
        self.local_start=None;self.local=None
    def add(self,value,index,thresholds):
        d=self.durations[index];marked=self.marked[index]
        result=[]
        for need in range(self.needed+1):
            current=value[need]
            source=value[max(0,need-marked)]
            if source and d<thresholds[need]:
                current=(current|(source<<d))&self.mask
                thresholds[need]=(self.mask^current).bit_length()
            result.append(current)
        return tuple(result)
    def suffix_at(self,index,needed=0):
        count=len(self.tracks)
        if index==count:return self.suffix[count][needed]
        start=(index//self.block)*self.block
        if self.local_start!=start:
            stop=min(start+self.block,count)
            local=[None]*(stop-start+1);local[-1]=self.suffix[stop]
            thresholds=[(self.mask^v).bit_length() for v in local[-1]]
            for i in range(stop-1,start-1,-1):local[i-start]=self.add(local[i-start+1],i,thresholds)
            self.local_start=start;self.local=local
        return self.local[index-start][needed]


def finish_pivot_core_dfs(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats):
    pivot_indices=[i for i in free if scores[i]==pivot]
    other=[i for i in free if scores[i]!=pivot]
    if not pivot_indices or len(other)>36:return None
    residual=target-sum(candidates[i]['duration_ms'] for i in forced_in)
    if residual<0:return None
    try:oracle=SumOracle([candidates[i] for i in pivot_indices],residual,deadline)
    except OverflowError:return None
    costs=[abs(scores[i]-pivot)*candidates[i]['duration_ms'] for i in other]
    denominator=lcm(*(v.denominator for v in costs))
    costs=[int(v*denominator) for v in costs]
    best_cost=int((upper-lower)*denominator)
    count=len(candidates)
    masks=[1<<(count-1-i) for i in other]
    fixed_mask=sum(1<<(count-1-i) for i in forced_in)
    selected_mask=sum(mask for mask,i in zip(masks,other) if scores[i]>pivot)
    selected_ms=sum(candidates[i]['duration_ms'] for i in other if scores[i]>pivot)
    signed=[-candidates[i]['duration_ms'] if scores[i]>pivot else candidates[i]['duration_ms'] for i in other]
    global_masks={t['track_id']:1<<(count-1-i) for i,t in enumerate(candidates)}
    best_mask=sum(global_masks[key] for key in hint)
    found=bool(hint)
    items=sorted((cost,signed[j],-masks[j] if scores[i]>pivot else masks[j]) for j,(i,cost) in enumerate(zip(other,costs)))
    try:state_count=budget_count(items,best_cost,min(deadline,monotonic()+.15),cap=2000000)
    except TimeoutError:return None
    if state_count>2000000:return None
    work=0
    def states(start=0,loss=0,delta=0,change=0):
        nonlocal work
        work+=1
        if work%4096==0 and monotonic()>=deadline:raise TimeoutError('pivot deviations deadline')
        yield loss,delta,change
        for j in range(start,len(items)):
            cost,duration,mask=items[j]
            if loss+cost>best_cost:break
            yield from states(j+1,loss+cost,delta+duration,change+mask)
    for loss,delta,change in states():
        current_ms=selected_ms+delta
        if loss>best_cost or not oracle.possible(residual-current_ms):continue
        chosen=oracle.subset(residual-current_ms)
        full_mask=fixed_mask+selected_mask+change+sum(global_masks[t['track_id']] for t in chosen)
        if not found or loss<best_cost or (loss==best_cost and full_mask>best_mask):
            best_cost=loss;best_mask=full_mask
        found=True
    if not found:
        stats['pivot_proven_empty']=True;return None
    result=[t for i,t in enumerate(candidates) if best_mask>>(count-1-i)&1]
    assert sum(t['duration_ms'] for t in result)==target
    assert upper-sum(scores[i]*candidates[i]['duration_ms'] for i in range(count) if best_mask>>(count-1-i)&1)==Fraction(best_cost,denominator)
    stats.update({'method':'plateau_loss_exact','plateau_score':str(pivot),'pivot_variables':len(pivot_indices),'other_variables':len(other),
                  'deviation_states':work,'oracle_bytes_bound':oracle.bytes_bound})
    return result


def finish_pivot_core(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats):
    """Batch loss states and reconstruct plateau subsets only for minimum loss."""
    import numpy as np
    pivot_indices=[i for i in free if scores[i]==pivot];other=[i for i in free if scores[i]!=pivot]
    residual=target-sum(candidates[i]['duration_ms'] for i in forced_in)
    if residual<0:stats['pivot_proven_empty']=True;return None
    losses=[abs(scores[i]-pivot)*candidates[i]['duration_ms'] for i in other]
    denominator=lcm(*(v.denominator for v in losses));coefficients=[int(v*denominator) for v in losses]
    common=gcd(*coefficients) or 1;coefficients=[v//common for v in coefficients]
    if sum(coefficients)>=2**61:return finish_pivot_core_dfs(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats)
    budget=min(sum(coefficients),int((upper-lower)*denominator//common))
    if budget<0:stats['pivot_proven_empty']=True;return None
    preferred_mask=sum(1<<(len(other)-1-j) for j,i in enumerate(other) if scores[i]>pivot)
    preferred_ms=sum(candidates[i]['duration_ms'] for i in other if scores[i]>pivot)
    words=max(1,(len(other)+63)//64);state_limit=min(2000000,(96*1024*1024)//(16+8*words))
    costs=np.zeros(1,dtype=np.int64);delta=np.zeros(1,dtype=np.int64)
    masks=[np.array([(preferred_mask>>(64*word))&((1<<64)-1)],dtype=np.uint64) for word in range(words)]
    for j in sorted(range(len(other)),key=lambda j:-coefficients[j]):
        if monotonic()>=deadline:raise TimeoutError('plateau array states deadline')
        include=costs<=budget-coefficients[j]
        if len(costs)+int(include.sum())>state_limit:return None
        i=other[j];duration=-candidates[i]['duration_ms'] if scores[i]>pivot else candidates[i]['duration_ms']
        costs=np.concatenate((costs,costs[include]+coefficients[j]))
        delta=np.concatenate((delta,delta[include]+duration))
        position=len(other)-1-j
        for word in range(words):
            extension=masks[word][include]
            if word==position//64:extension=extension^np.uint64(1<<(position%64))
            masks[word]=np.concatenate((masks[word],extension))
    if pivot_indices:
        try:oracle=SumOracle([candidates[i] for i in pivot_indices],residual,deadline)
        except OverflowError:return None
    else:oracle=None
    wanted=residual-preferred_ms-delta
    if oracle is None:indices=np.flatnonzero(wanted==0)
    else:
        valid=(wanted>=0)&(wanted<=oracle.upper*oracle.unit)&(wanted%oracle.unit==0);indices=np.flatnonzero(valid)
        goals=wanted[indices]//oracle.unit;blob=np.frombuffer(oracle.bits,dtype=np.uint8)
        indices=indices[((blob[goals//8]>>(goals%8))&1)!=0]
    if not len(indices):stats['pivot_proven_empty']=True;return None
    minimum=int(costs[indices].min());indices=indices[costs[indices]==minimum]
    count=len(candidates);fixed_mask=sum(1<<(count-1-i) for i in forced_in)
    global_bits={t['track_id']:1<<(count-1-i) for i,t in enumerate(candidates)};best_mask=-1
    for index in indices:
        if monotonic()>=deadline:raise TimeoutError('plateau array lex deadline')
        selected_mask=sum(int(masks[word][index])<<(64*word) for word in range(words));chosen=oracle.subset(int(wanted[index])) if oracle is not None else []
        full_mask=fixed_mask+sum(1<<(count-1-i) for j,i in enumerate(other) if selected_mask>>(len(other)-1-j)&1)+sum(global_bits[t['track_id']] for t in chosen)
        best_mask=max(best_mask,full_mask)
    result=[t for i,t in enumerate(candidates) if best_mask>>(count-1-i)&1]
    assert sum(t['duration_ms'] for t in result)==target
    assert upper-sum(scores[i]*candidates[i]['duration_ms'] for i in range(count) if best_mask>>(count-1-i)&1)==Fraction(minimum*common,denominator)
    stats.update(method='plateau_loss_array_exact' if oracle is not None else 'loss_array_exact',plateau_score=str(pivot),pivot_variables=len(pivot_indices),other_variables=len(other),
                 deviation_states=len(costs),plateau_optimal_states=len(indices),oracle_bytes_bound=oracle.bytes_bound if oracle is not None else 0)
    return result


def plateau_reduced_exact(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats):
    """Factor the largest equal-score group before expanding loss states."""
    if free:
        anchor=Counter(scores[i] for i in free).most_common(1)[0][0]
        if anchor!=pivot:
            fixed_quality=sum(scores[i]*candidates[i]['duration_ms'] for i in forced_in)
            residual=target-sum(candidates[i]['duration_ms'] for i in forced_in)
            alternate=fixed_quality+anchor*residual+sum(max(Fraction(0),(scores[i]-anchor)*candidates[i]['duration_ms']) for i in free)
            stats['plateau_first']=str(anchor)
            result=finish_pivot_core(candidates,scores,anchor,alternate,lower,forced_in,free,hint,target,deadline,stats)
            if result is not None or stats.get('pivot_proven_empty'):return result
    return finish_pivot_core(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats)


def budget_items(candidates,scores,pivot,free,gap):
    costs=[abs(scores[i]-pivot)*candidates[i]['duration_ms'] for i in free]
    denominator=lcm(*(v.denominator for v in costs))
    coefficients=[int(v*denominator) for v in costs]
    common=gcd(*coefficients) or 1
    coefficients=[v//common for v in coefficients]
    budget=int(gap*denominator//common)
    count=len(free)
    items=[(cost,-candidates[i]['duration_ms'] if scores[i]>pivot else candidates[i]['duration_ms'],
            (-1 if scores[i]>pivot else 1)*(1<<(count-1-j))) for j,(i,cost) in enumerate(zip(free,coefficients))]
    items.sort(reverse=True)
    halves=[sorted(items[::2]),sorted(items[1::2])]
    return halves,budget


def budget_count(items,budget,deadline,cap=1500000):
    suffix=[0]*(len(items)+1)
    for i in range(len(items)-1,-1,-1):suffix[i]=suffix[i+1]+items[i][0]
    calls=0
    @lru_cache(maxsize=100000)
    def count(start,remaining):
        nonlocal calls
        calls+=1
        if calls%2048==0 and monotonic()>=deadline:raise TimeoutError('bounded count deadline')
        if suffix[start]<=remaining:return min(cap+1,1<<(len(items)-start))
        total=1
        for j in range(start,len(items)):
            cost=items[j][0]
            if cost>remaining:break
            total+=count(j+1,remaining-cost)
            if total>cap:return cap+1
        return total
    return count(0,budget)


def finish_bounded_core(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats):
    halves,budget=budget_items(candidates,scores,pivot,free,upper-lower)
    try:
        count_deadline=min(deadline,monotonic()+.25)
        counts=[budget_count(items,budget,count_deadline) for items in halves]
    except TimeoutError:
        stats['bounded_declined']='count_budget';return None
    stats['bounded_states']=counts
    if max(counts)>1500000:return None
    if counts[0]>counts[1]:halves.reverse();counts.reverse()
    until=min(deadline,monotonic()+2.5)
    work=0
    def states(items,start=0,cost=0,duration=0,change=0):
        nonlocal work
        work+=1
        if work%4096==0 and monotonic()>=until:raise TimeoutError('bounded enumeration deadline')
        yield cost,duration,change
        for j in range(start,len(items)):
            item=items[j]
            if cost+item[0]>budget:break
            yield from states(items,j+1,cost+item[0],duration+item[1],change+item[2])
    left={}
    try:
        for cost,duration,change in states(halves[0]):
            previous=left.get(duration)
            if previous is None or cost<previous[0] or (cost==previous[0] and change>previous[1]):left[duration]=(cost,change)
        preferred=forced_in+[i for i in free if scores[i]>pivot]
        base_mask=sum(1<<(len(free)-1-j) for j,i in enumerate(free) if scores[i]>pivot)
        delta=target-sum(candidates[i]['duration_ms'] for i in preferred)
        best_mask=sum(1<<(len(free)-1-j) for j,i in enumerate(free) if candidates[i]['track_id'] in hint)
        found=bool(hint)
        for cost,duration,change in states(halves[1]):
            match=left.get(delta-duration)
            if match is None or cost+match[0]>budget:continue
            loss=cost+match[0];mask=base_mask+change+match[1]
            if not found or loss<budget or (loss==budget and mask>best_mask):budget=loss;best_mask=mask
            found=True
    except TimeoutError:
        stats.update({'bounded_declined':'enumeration_budget','bounded_work':work});return None
    if not found:
        stats['bounded_proven_empty']=True;return None
    result=[candidates[i] for i in forced_in]+[candidates[i] for j,i in enumerate(free) if best_mask>>(len(free)-1-j)&1]
    assert sum(t['duration_ms'] for t in result)==target
    assert sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in result)>=lower
    stats.update({'method':'loss_bounded_exact','bounded_work':work,'bounded_duration_states':len(left)})
    return result


def finish_optimal_face(candidates,scores,pivot,upper,optimum_loss,forced_in,free,hint,target,deadline,stats):
    newly_forced=[i for i in free if abs(scores[i]-pivot)*candidates[i]['duration_ms']>optimum_loss]
    reduced=[i for i in free if i not in set(newly_forced)]
    forced=forced_in+[i for i in newly_forced if scores[i]>pivot]
    stats['optimal_face_free']=len(reduced)
    lower=upper-optimum_loss
    if len(reduced)<=44:
        weights=[scores[i]*candidates[i]['duration_ms'] for i in reduced]
        denominator=lcm(*(w.denominator for w in weights))
        coefficients=[int(w*denominator) for w in weights]
        answer=numpy_subset([candidates[i] for i in reduced],coefficients,
                            target-sum(candidates[i]['duration_ms'] for i in forced),deadline,44)
        assert answer is not None
        result=[candidates[i] for i in forced]+answer[0]
        assert sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in result)==lower
        stats['method']='optimal_face_array'
        return result
    return None


def modular_reduce(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats):
    """Minimum exact loss for each duration residue proves more fixed decisions."""
    import numpy as np
    if not free:return (candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats)
    costs=[abs(scores[i]-pivot)*candidates[i]['duration_ms'] for i in free]
    denominator=lcm(*(v.denominator for v in costs))
    coefficients=[int(v*denominator) for v in costs]
    common=gcd(*coefficients) or 1;coefficients=[v//common for v in coefficients]
    budget=int((upper-lower)*denominator//common)
    if sum(coefficients)>=2**61:return (candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats)
    modulus=10000 if (len(free)+1)*10000*16<=96*1024*1024 else 1000
    preferred=forced_in+[i for i in free if scores[i]>pivot]
    delta=target-sum(candidates[i]['duration_ms'] for i in preferred)
    signed=[-candidates[i]['duration_ms'] if scores[i]>pivot else candidates[i]['duration_ms'] for i in free]
    infinity=budget+1
    prefix=np.full((len(free)+1,modulus),infinity,dtype=np.int64);prefix[0,0]=0
    suffix=np.full_like(prefix,infinity);suffix[-1,0]=0
    for j,(cost,duration) in enumerate(zip(coefficients,signed)):
        if j%16==0 and monotonic()>=deadline:raise TimeoutError('modular forward deadline')
        prefix[j+1]=np.minimum(prefix[j],np.minimum(infinity,np.roll(prefix[j],duration%modulus)+cost))
    for j in range(len(free)-1,-1,-1):
        suffix[j]=np.minimum(suffix[j+1],np.minimum(infinity,np.roll(suffix[j+1],signed[j]%modulus)+coefficients[j]))
    residue=delta%modulus
    if int(prefix[-1,residue])>budget and stats.get('cutoff_mode'):
        stats['modular_proven_empty']=True;return None
    assert int(prefix[-1,residue])<=budget
    fixed=list(forced_in);remaining=[];fixed_loss=0;opposite=0
    lookup=(residue-np.arange(modulus))%modulus
    for j,(i,cost,duration) in enumerate(zip(free,coefficients,signed)):
        if j%16==0 and monotonic()>=deadline:raise TimeoutError('modular fixing deadline')
        preferred_min=int(np.min(prefix[j]+suffix[j+1][lookup]))
        flipped_min=cost+int(np.min(prefix[j]+suffix[j+1][(lookup-duration)%modulus]))
        assert preferred_min<=budget or flipped_min<=budget
        if preferred_min>budget:
            fixed_loss+=cost;opposite+=1
            if scores[i]<=pivot:fixed.append(i)
        elif flipped_min>budget:
            if scores[i]>pivot:fixed.append(i)
        else:remaining.append(i)
    updated_upper=upper-Fraction(fixed_loss*common,denominator)
    gap=updated_upper-lower
    final=[]
    for i in remaining:
        if abs(scores[i]-pivot)*candidates[i]['duration_ms']>gap:
            if scores[i]>pivot:fixed.append(i)
        else:final.append(i)
    stats.update({'modulus':modulus,'modular_before':len(free),'modular_after':len(final),
                  'modular_opposite':opposite,'modular_loss_floor':str(Fraction(int(prefix[-1,residue])*common,denominator))})
    return candidates,scores,pivot,updated_upper,lower,fixed,final,hint,target,deadline,stats


def strong_modular_reduce(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats,modulus=1000000):
    """Admissible quantized lower bounds; all final decisions remain exact.

    Loss costs are rounded down only inside this pruning bound. A choice is
    fixed only when this weaker bound already exceeds the feasible budget.
    Suffix checkpoints keep the million-residue bound below 100 MiB.
    """
    import numpy as np
    if not free:return candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats
    costs=[abs(scores[i]-pivot)*candidates[i]['duration_ms'] for i in free]
    denominator=lcm(*(v.denominator for v in costs));exact=[int(v*denominator) for v in costs]
    common=gcd(*exact) or 1;exact=[v//common for v in exact]
    budget=int((upper-lower)*denominator//common)
    scale=max(1,(budget+65532)//65533);bound_budget=budget//scale;infinity=bound_budget+1
    coefficients=[min(infinity,v//scale) for v in exact]
    preferred=forced_in+[i for i in free if scores[i]>pivot]
    delta=target-sum(candidates[i]['duration_ms'] for i in preferred)
    signed=[-candidates[i]['duration_ms'] if scores[i]>pivot else candidates[i]['duration_ms'] for i in free]
    count=len(free);block=max(1,isqrt(count));bytes_bound=(count//block+block+6)*modulus*2
    if bytes_bound>100*1024*1024:return candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats
    def advance(value,j):
        cost=coefficients[j]
        added=np.add(np.minimum(np.roll(value,signed[j]%modulus),infinity-cost),cost,dtype=np.uint16)
        return np.minimum(value,added)
    start=monotonic();initial=np.full(modulus,infinity,dtype=np.uint16);initial[0]=0
    value=initial;suffix={count:value}
    for j in range(count-1,-1,-1):
        if j%4==0 and monotonic()>=deadline:raise TimeoutError('strong modular suffix deadline')
        value=advance(value,j)
        if j%block==0:suffix[j]=value
    residue=delta%modulus;assert int(value[residue])<=bound_budget
    floor=int(value[residue]);lookup=(residue-np.arange(modulus))%modulus
    prefix=initial;fixed=list(forced_in);remaining=[];fixed_loss=Fraction(0);opposite=0
    for start_index in range(0,count,block):
        stop=min(start_index+block,count);local=[None]*(stop-start_index+1);local[-1]=suffix[stop]
        for j in range(stop-1,start_index-1,-1):local[j-start_index]=advance(local[j-start_index+1],j)
        for j in range(start_index,stop):
            if monotonic()>=deadline:raise TimeoutError('strong modular fixing deadline')
            right=local[j-start_index+1]
            preferred_min=int(np.min(np.add(prefix,right[lookup],dtype=np.uint32)))
            flipped_min=coefficients[j]+int(np.min(np.add(prefix,right[(lookup-signed[j])%modulus],dtype=np.uint32)))
            assert preferred_min<=bound_budget or flipped_min<=bound_budget
            i=free[j]
            if preferred_min>bound_budget:
                fixed_loss+=costs[j];opposite+=1
                if scores[i]<=pivot:fixed.append(i)
            elif flipped_min>bound_budget:
                if scores[i]>pivot:fixed.append(i)
            else:remaining.append(i)
            prefix=advance(prefix,j)
    updated_upper=upper-fixed_loss;gap=updated_upper-lower;final=[]
    for i in remaining:
        if abs(scores[i]-pivot)*candidates[i]['duration_ms']>gap:
            if scores[i]>pivot:fixed.append(i)
        else:final.append(i)
    stats.update(strong_modular_before=count,strong_modular_after=len(final),strong_modular_opposite=opposite,
                 strong_modular_scale=scale,strong_modular_bytes_bound=bytes_bound,strong_modular_seconds=monotonic()-start,
                 strong_modular_floor=str(Fraction(floor*scale*common,denominator)))
    return candidates,scores,pivot,updated_upper,lower,fixed,final,hint,target,deadline,stats


def improve_incumbent(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats):
    costs=[abs(scores[i]-pivot)*candidates[i]['duration_ms'] for i in free]
    denominator=lcm(*(v.denominator for v in costs));coefficients=[int(v*denominator) for v in costs]
    common=gcd(*coefficients) or 1;coefficients=[v//common for v in coefficients]
    if sum(coefficients)>=2**61:return None
    model=cp_model.CpModel();xs=[model.NewBoolVar(f'probe{i}') for i in free]
    model.Add(sum(x*candidates[i]['duration_ms'] for x,i in zip(xs,free))==target-sum(candidates[i]['duration_ms'] for i in forced_in))
    loss=sum((1-x if scores[i]>pivot else x)*cost for x,i,cost in zip(xs,free,coefficients))
    model.Add(loss<=int((upper-lower)*denominator//common));model.Minimize(loss)
    for x,i in zip(xs,free):model.AddHint(x,int(candidates[i]['track_id'] in hint))
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
    solver.parameters.max_time_in_seconds=max(.001,min(1.5,deadline-monotonic()))
    phase='quality_probe';status=solver.Solve(model)
    stats['quality_probe_done']=True;stats['quality_probe_status']=solver.StatusName(status)
    if status not in (cp_model.FEASIBLE,cp_model.OPTIMAL):return None
    chosen=forced_in+[i for x,i in zip(xs,free) if solver.Value(x)]
    assert sum(candidates[i]['duration_ms'] for i in chosen)==target
    quality=sum(scores[i]*candidates[i]['duration_ms'] for i in chosen)
    assert quality>=lower
    stats['quality_probe_lower']=str(quality)
    if status==cp_model.OPTIMAL:stats['quality_probe_optimum']=True
    if quality==lower and status!=cp_model.OPTIMAL:return None
    fixed=list(forced_in);remaining=[];gap=upper-quality
    for i in free:
        if abs(scores[i]-pivot)*candidates[i]['duration_ms']>gap:
            if scores[i]>pivot:fixed.append(i)
        else:remaining.append(i)
    stats['quality_probe_free']=len(remaining)
    return candidates,scores,pivot,upper,quality,fixed,remaining,{candidates[i]['track_id'] for i in chosen},target,deadline,stats


def necessary_genre_tracks(ordered,genres,representatives):
    assigned=representatives(ordered,genres)
    if assigned is None:return None
    forced=[]
    for key in assigned.values():
        if representatives([t for t in ordered if t['track_id']!=key],genres) is None:forced.append(key)
    return set(forced)


def deficient_genres(chosen,genres):
    by_id={t['track_id']:set(t['genre_group_codes']) for t in chosen}
    assigned={}
    def augment(genre,seen,reached):
        reached.add(genre)
        for key,groups in by_id.items():
            if key in seen or genre not in groups:continue
            seen.add(key)
            if key not in assigned or augment(assigned[key],seen,reached):
                assigned[key]=genre;return True
        return False
    for genre in genres:
        reached=set()
        if not augment(genre,set(),reached):return reached
    return set()


def lex_genre_partition(ordered,target,genres,deadline,representatives,stats,initial_forced=()):
    """Partition only the missing genre choices; each node has an exact lex bound."""
    global_bits={t['track_id']:1<<(len(ordered)-1-i) for i,t in enumerate(ordered)}
    best_mask=-1;best=None
    def visit(forced,excluded):
        nonlocal best_mask,best
        if monotonic()>=deadline:raise TimeoutError('genre partition deadline')
        stats['genre_nodes']=stats.get('genre_nodes',0)+1
        available=[t for t in ordered if t['track_id'] not in excluded]
        necessary=necessary_genre_tracks(available,genres,representatives)
        if necessary is None:return
        forced=forced|necessary
        first=[t for t in available if t['track_id'] in forced]
        residual=target-sum(t['duration_ms'] for t in first)
        rest=[t for t in available if t['track_id'] not in forced]
        handled,chosen=exact_bits(rest,residual,deadline)
        if not handled:raise OverflowError('genre bitset memory gate')
        if chosen is None:return
        chosen=first+chosen
        bound=sum(global_bits[t['track_id']] for t in chosen)
        if bound<=best_mask:return
        deficient=deficient_genres(chosen,genres)
        if not deficient:
            best_mask=bound;best=chosen;return
        chosen_ids={t['track_id'] for t in chosen}
        cut=[t['track_id'] for t in available if t['track_id'] not in chosen_ids and deficient.intersection(t['genre_group_codes'])]
        prior=set(excluded)
        for key in cut:
            visit(forced|{key},prior)
            prior=prior|{key}
    visit(set(initial_forced),set())
    if best is not None:stats['genre_partition_certified']=True
    return best


def lex_genre_dfs(ordered,target,genres,deadline,representatives,stats,initial_forced=()):
    """Global lex DFS shares suffix bitsets and reserves time for missing genres."""
    necessary=necessary_genre_tracks(ordered,genres,representatives)
    if necessary is None:return None
    forced=set(initial_forced)|necessary
    first=tuple(t for t in ordered if t['track_id'] in forced)
    tracks=[t for t in ordered if t['track_id'] not in forced]
    residual=target-sum(t['duration_ms'] for t in first)
    if residual<0:return None
    if not tracks:
        return list(first) if residual==0 and representatives(first,genres) is not None else None
    oracle=SumOracle(tracks,residual,deadline)
    codes={g:1<<i for i,g in enumerate(genres)};full=(1<<len(genres))-1
    def genre_mask(track):return sum(value for g,value in codes.items() if g in track['genre_group_codes'])
    masks=[genre_mask(t) for t in tracks]
    patterns=sorted(set(masks+[genre_mask(t) for t in first]))
    by_pattern={mask:i for i,mask in enumerate(patterns)}
    counts=[0]*len(patterns);covered=0
    for t in first:
        mask=genre_mask(t);counts[by_pattern[mask]]+=1;covered|=mask
    suffix_min=[None]*(len(tracks)+1)
    suffix_min[-1]=(target+1,)*len(genres)
    suffix_cover=[0]*(len(tracks)+1)
    for i in range(len(tracks)-1,-1,-1):
        minima=list(suffix_min[i+1]);mask=masks[i]
        # Splitting one track's duration over its genres gives a safe lower
        # bound on the extra duration needed to cover all absent genres.
        discounted=tracks[i]['duration_ms']//max(1,mask.bit_count())
        for j in range(len(genres)):
            if mask>>j&1:minima[j]=min(minima[j],discounted)
        suffix_min[i]=tuple(minima);suffix_cover[i]=suffix_cover[i+1]|mask
    stack=[(0,residual,first,covered,tuple(counts))]
    visited=set()
    while stack:
        if monotonic()>=deadline:raise TimeoutError('genre lex DFS deadline')
        i,remaining,chosen,covered,signature=stack.pop()
        stats['genre_nodes']=stats.get('genre_nodes',0)+1
        key=(i,remaining,signature)
        if key in visited:continue
        visited.add(key)
        if covered|suffix_cover[i]!=full:continue
        absent=full^covered
        reserve=sum(value for j,value in enumerate(suffix_min[i]) if absent>>j&1)
        if remaining<reserve or not oracle.possible_from(i,remaining):continue
        if covered==full and representatives(chosen,genres) is not None:
            result=list(chosen)+oracle.subset_from(i,remaining)
            stats.update({'genre_partition_certified':True,'oracle_bytes_bound':oracle.bytes_bound,
                          'genre_visited_states':len(visited)})
            return result
        if remaining==0 or i==len(tracks):continue
        # Exclude is visited only after the lexicographically larger include.
        stack.append((i+1,remaining,chosen,covered,signature))
        track=tracks[i];duration=track['duration_ms']
        if duration<=remaining:
            next_signature=list(signature);j=by_pattern[masks[i]]
            next_signature[j]=min(len(genres),next_signature[j]+1)
            stack.append((i+1,remaining-duration,chosen+(track,),covered|masks[i],tuple(next_signature)))
    return None


def prefix_witness(ordered,target,genres,forced,deadline,representatives):
    """Find a feasible hint that includes a long run of earliest lex tracks."""
    fixed=[t for t in ordered if t['track_id'] in forced]
    rest=[t for t in ordered if t['track_id'] not in forced]
    short=sorted(rest,key=lambda t:t['duration_ms'])
    for slack in (500000,1000000):
        best=None;prefix=[];prefix_ids=set();prefix_ms=sum(t['duration_ms'] for t in fixed)
        for track in rest[:256]:
            if monotonic()>=deadline:return None
            prefix.append(track);prefix_ids.add(track['track_id']);prefix_ms+=track['duration_ms']
            if prefix_ms>target-slack:break
            assignment=representatives(fixed+prefix+[t for t in short if t['track_id'] not in prefix_ids],genres)
            if assignment is None:return None
            required=forced|prefix_ids|set(assignment.values())
            chosen=[t for t in ordered if t['track_id'] in required]
            if sum(t['duration_ms'] for t in chosen)<=target-slack:best=chosen
        if best is None:continue
        chosen_ids={t['track_id'] for t in best}
        remaining=[t for t in ordered if t['track_id'] not in chosen_ids]
        try:handled,extra=exact_bits(remaining,target-sum(t['duration_ms'] for t in best),deadline)
        except TimeoutError:return None
        if handled and extra is not None:
            result=best+extra
            assert sum(t['duration_ms'] for t in result)==target and representatives(result,genres) is not None
            return result
    return None


def lex_genre_subset_single(ordered,target,genres,deadline,representatives,stats,initial_forced=(),rare_cap=22):
    """Join small rare-genre subset states with shared common-track suffix DP."""
    import numpy as np
    necessary=necessary_genre_tracks(ordered,genres,representatives)
    if necessary is None:return None
    forced=set(initial_forced)|necessary
    if len(ordered)>400:
        started=monotonic()
        hint=prefix_witness(ordered,target,genres,forced,min(deadline,started+1.5),representatives)
        stats['prefix_hint_seconds']=monotonic()-started
        if hint is not None:
            ids={t['track_id'] for t in hint};count=0
            for t in ordered:
                if t['track_id'] in forced:continue
                if t['track_id'] not in ids:break
                forced.add(t['track_id']);count+=1
            stats['prefix_hint_fixed']=count
    first=[t for t in ordered if t['track_id'] in forced]
    rest=[t for t in ordered if t['track_id'] not in forced]
    residual=target-sum(t['duration_ms'] for t in first)
    if residual<0:return None
    counts=Counter(g for t in ordered for g in t['genre_group_codes'])
    restricted={g for g in genres if counts[g]<=4}
    if len(ordered)>400:
        for g in sorted(genres,key=lambda g:counts[g]):
            trial=restricted|{g}
            if sum(bool(trial.intersection(t['genre_group_codes'])) for t in rest)<=rare_cap:restricted=trial
    hall_cut=None
    if len(ordered)>400:
        outside=[g for g in genres if g not in restricted]
        if outside:hall_cut={min(outside,key=lambda g:counts[g])}
    for attempt in range(len(genres)+1):
        if monotonic()>=deadline:raise TimeoutError('rare genre join deadline')
        rare=[t for t in rest if restricted.intersection(t['genre_group_codes'])]
        common=[t for t in rest if not restricted.intersection(t['genre_group_codes'])]
        stats.update({'active_join_attempt':attempt+1,'active_hall_cut':sorted(hall_cut or []),
                      'active_rare_tracks':len(rare),'active_common_tracks':len(common),'active_genre_phase':'state_table'})
        if len(rare)>rare_cap:
            stats['rare_state_gate']=len(rare)
            return lex_genre_dfs(ordered,target,genres,deadline,representatives,stats,initial_forced)
        size=1<<len(rare)
        durations=np.empty(size,dtype=np.int64);durations[0]=0
        states=np.arange(size,dtype=np.int64)
        length=1
        for t in reversed(rare):
            durations[length:2*length]=durations[:length]+t['duration_ms'];length*=2
        valid=durations<=residual
        # Hall inequalities are necessary and sufficient for distinct genre reps.
        # Disconnected genre components can be checked independently.
        groups=sorted(restricted)
        neighbors={g:{g} for g in groups}
        for t in first+rare:
            connected=set(t['genre_group_codes'])&restricted
            for g in connected:neighbors[g]|=connected
        components=[];unseen=set(groups)
        while unseen:
            todo=[unseen.pop()];component=set()
            while todo:
                g=todo.pop();component.add(g)
                adjacent=neighbors[g]&unseen;unseen-=adjacent;todo.extend(adjacent)
            components.append(sorted(component))
        lut=np.array([i.bit_count() for i in range(1<<16)],dtype=np.uint8)
        for component in components:
            if len(component)>10:return lex_genre_dfs(ordered,target,genres,deadline,representatives,stats,initial_forced)
            for mask in range(1,1<<len(component)):
                subset={g for j,g in enumerate(component) if mask>>j&1}
                required=len(subset)-sum(bool(subset.intersection(t['genre_group_codes'])) for t in first)
                if required<=0:continue
                union=sum(1<<(len(rare)-1-j) for j,t in enumerate(rare) if subset.intersection(t['genre_group_codes']))
                bits=states&union
                population=lut[bits&65535]+lut[bits>>16]
                valid &= population>=required
        states=states[valid];durations=durations[valid]
        del valid,lut
        if not len(states):return None
        if not common:
            possible=durations==residual
            states=states[possible];durations=durations[possible]
            if not len(states):return None
            state=int(states.max());chosen=first+[t for j,t in enumerate(rare) if state>>(len(rare)-1-j)&1]
        else:
            if hall_cut:
                fixed_count=sum(bool(hall_cut.intersection(t['genre_group_codes'])) for t in first)
                union=sum(1<<(len(rare)-1-j) for j,t in enumerate(rare) if hall_cut.intersection(t['genre_group_codes']))
                lut=np.array([i.bit_count() for i in range(1<<16)],dtype=np.uint8)
                bits=states&union
                selected=lut[bits&65535]+lut[bits>>16]
                needs=np.maximum(0,len(hall_cut)-fixed_count-selected.astype(np.int16))
                if int(needs.max())>3:return lex_genre_dfs(ordered,target,genres,deadline,representatives,stats,initial_forced)
                if not np.any(needs):hall_cut=None
                stats['active_genre_phase']='count_dp'
                stats['active_count_needed']=int(needs.max())
                before_dp=monotonic()
                oracle=CountSumOracle(common,residual,deadline,hall_cut,int(needs.max())) if hall_cut else SumOracle(common,residual,deadline)
            else:
                needs=np.zeros(len(states),dtype=np.int16)
                stats['active_genre_phase']='plain_dp'
                before_dp=monotonic()
                oracle=SumOracle(common,residual,deadline)
            stats['last_dp_seconds']=monotonic()-before_dp
            stats['active_genre_phase']='lex_join'
            remaining=residual-durations
            def possible_from(index,values,requirements):
                good=(values>=0)&(values<=oracle.upper*oracle.unit)&(values%oracle.unit==0)
                indices=np.flatnonzero(good)
                if len(indices):
                    for required in np.unique(requirements[indices]):
                        part=indices[requirements[indices]==required]
                        goals=values[part]//oracle.unit
                        value=oracle.suffix_at(index,int(required)) if hall_cut else oracle.suffix_at(index)
                        blob=np.frombuffer(value.to_bytes((oracle.upper+8)//8,'little'),dtype=np.uint8)
                        good[part]=((blob[goals//8]>>(goals%8))&1)!=0
                return good
            good=possible_from(0,remaining,needs)
            states=states[good];remaining=remaining[good];needs=needs[good]
            if not len(states):return None
            rare_index={t['track_id']:len(rare)-1-j for j,t in enumerate(rare)}
            common_index=0;chosen_common=[]
            for t in rest:
                if monotonic()>=deadline:raise TimeoutError('rare genre lex deadline')
                if t['track_id'] in rare_index:
                    include=((states>>rare_index[t['track_id']])&1)!=0
                    next_needs=needs
                else:
                    common_index+=1
                    next_needs=np.maximum(0,needs-int(bool(hall_cut and hall_cut.intersection(t['genre_group_codes']))))
                    include=possible_from(common_index,remaining-t['duration_ms'],next_needs)
                if np.any(include):
                    states=states[include];remaining=remaining[include];needs=next_needs[include]
                    if t['track_id'] not in rare_index:
                        chosen_common.append(t);remaining-=t['duration_ms']
            assert len(states)==1 and int(remaining[0])==0 and int(needs[0])==0
            state=int(states[0]);chosen=first+chosen_common+[t for j,t in enumerate(rare) if state>>(len(rare)-1-j)&1]
        missing=deficient_genres(chosen,genres)
        stats.update({'genre_join_attempts':attempt+1,'rare_tracks':len(rare),'rare_states':size,
                      'restricted_genres':sorted(restricted),'hall_cut':sorted(hall_cut or [])})
        if not missing:
            stats['genre_partition_certified']=True
            return chosen
        if missing<=restricted:return None
        next_restricted=restricted|missing
        next_size=sum(bool(next_restricted.intersection(t['genre_group_codes'])) for t in rest)
        if next_size>rare_cap and hall_cut is None:
            hall_cut=missing
        elif next_size>rare_cap and hall_cut is not None:
            return lex_genre_dfs(ordered,target,genres,deadline,representatives,stats,initial_forced)
        else:restricted=next_restricted
    return None


class MultiCountSumOracle:
    """Exact suffix sums satisfying several Hall count inequalities together."""
    def __init__(self,tracks,maximum,deadline,cuts,maxima):
        import numpy as np
        self.tracks=tracks;self.deadline=deadline;self.cuts=cuts
        self.unit=gcd(*(t['duration_ms'] for t in tracks));self.upper=min(maximum,sum(t['duration_ms'] for t in tracks))//self.unit
        self.strides=[];size=1
        for bound in maxima:self.strides.append(size);size*=bound+1
        if size>64:raise OverflowError('Hall state budget')
        self.states=[None]*size
        for state in product(*(range(m+1) for m in maxima)):
            self.states[sum(v*s for v,s in zip(state,self.strides))]=state
        self.transitions=np.empty((1<<len(cuts),size),dtype=np.int64)
        for mask in range(1<<len(cuts)):
            for i,state in enumerate(self.states):
                self.transitions[mask,i]=sum(max(0,v-int(bool(mask>>j&1)))*self.strides[j] for j,v in enumerate(state))
        count=len(tracks);self.block=max(1,isqrt(count));self.mask=(1<<(self.upper+1))-1
        self.bytes_bound=(count//self.block+self.block+5)*(self.upper+1)*size//8
        if self.bytes_bound>384*1024*1024:raise OverflowError('multi-Hall memory budget')
        self.durations=[t['duration_ms']//self.unit for t in tracks]
        self.marked=[sum(1<<j for j,cut in enumerate(cuts) if cut.intersection(t['genre_group_codes'])) for t in tracks]
        value=(1,)+(0,)*(size-1);self.suffix={count:value};thresholds=[self.upper+1]*size
        for i in range(count-1,-1,-1):
            if monotonic()>=deadline:raise TimeoutError('multi-Hall build deadline')
            value=self.add(value,i,thresholds)
            if i%self.block==0:self.suffix[i]=value
        self.local_start=None;self.local=None
    def add(self,value,index,thresholds):
        d=self.durations[index];source_indices=self.transitions[self.marked[index]];result=[]
        for need,current in enumerate(value):
            source=value[int(source_indices[need])]
            if source and d<thresholds[need]:
                current=(current|(source<<d))&self.mask;thresholds[need]=(self.mask^current).bit_length()
            result.append(current)
        return tuple(result)
    def suffix_at(self,index,needed=0):
        count=len(self.tracks)
        if index==count:return self.suffix[count][needed]
        start=(index//self.block)*self.block
        if self.local_start!=start:
            stop=min(start+self.block,count);local=[None]*(stop-start+1);local[-1]=self.suffix[stop]
            thresholds=[(self.mask^v).bit_length() for v in local[-1]]
            for i in range(stop-1,start-1,-1):local[i-start]=self.add(local[i-start+1],i,thresholds)
            self.local_start=start;self.local=local
        return self.local[index-start][needed]


class SparseHallOracle:
    """Only reachable, nonredundant Hall states; logarithmic traceback space."""
    def __init__(self,tracks,maximum,cuts,initial,deadline,stats):
        import numpy as np
        self.tracks=tracks;self.deadline=deadline;self.cuts=cuts
        neighborhoods=[sum(1<<i for i,t in enumerate(tracks) if cut.intersection(t['genre_group_codes'])) for cut in cuts]
        self.implies=[(a,b) for a in range(len(cuts)) for b in range(len(cuts)) if a!=b and neighborhoods[a]&~neighborhoods[b]==0 and (neighborhoods[a]!=neighborhoods[b] or a<b)]
        self.pairs=[]
        for c in range(len(cuts)):
            for a in range(len(cuts)):
                for b in range(a):
                    if c not in (a,b) and not neighborhoods[a]&neighborhoods[b] and (neighborhoods[a]|neighborhoods[b])&~neighborhoods[c]==0:
                        self.pairs.append((a,b,c))
        @lru_cache(maxsize=8192)
        def canonical(state):
            values=list(state)
            for a,b in self.implies:
                if values[b] and values[a]>=values[b]:values[b]=0
            for a,b,c in self.pairs:
                if values[c] and values[a]+values[b]>=values[c]:values[c]=0
            return tuple(values)
        self.canonical=canonical
        self.marked=[sum(1<<j for j,cut in enumerate(cuts) if cut.intersection(t['genre_group_codes'])) for t in tracks]
        marks=sorted(set(self.marked));zero=(0,)*len(cuts)
        found={zero}|{canonical(tuple(int(v) for v in state)) for state in initial};todo=list(found)
        while todo:
            state=todo.pop()
            for mark in marks:
                next_state=canonical(tuple(max(0,v-int(bool(mark>>j&1))) for j,v in enumerate(state)))
                if next_state not in found:found.add(next_state);todo.append(next_state)
            if len(found)>512:raise OverflowError('sparse Hall states')
        self.states=sorted(found,key=lambda v:(sum(v),v));self.index={v:i for i,v in enumerate(self.states)}
        self.transitions={mark:np.array([self.index[canonical(tuple(max(0,v-int(bool(mark>>j&1))) for j,v in enumerate(state)))] for state in self.states],dtype=np.int64) for mark in marks}
        self.unit=gcd(*(t['duration_ms'] for t in tracks));self.upper=min(maximum,sum(t['duration_ms'] for t in tracks))//self.unit
        self.mask=(1<<(self.upper+1))-1;self.durations=[t['duration_ms']//self.unit for t in tracks]
        self.terminal=(1,)+(0,)*(len(self.states)-1)
        self.bytes_bound=(len(tracks).bit_length()+3)*(self.upper+1)*len(self.states)//8
        stats.update(sparse_hall_states=len(self.states),sparse_hall_bytes_bound=self.bytes_bound)
        if self.bytes_bound>384*1024*1024:raise OverflowError('sparse Hall memory')
    def add(self,value,index,thresholds):
        result=[];duration=self.durations[index];transition=self.transitions[self.marked[index]]
        for needed,current in enumerate(value):
            source=value[int(transition[needed])]
            if source and duration<thresholds[needed]:
                current=(current|(source<<duration))&self.mask;thresholds[needed]=(self.mask^current).bit_length()
            result.append(current)
        return tuple(result)
    def build(self,start,stop,tail):
        value=tail;thresholds=[(self.mask^v).bit_length() for v in value]
        for i in range(stop-1,start-1,-1):
            if monotonic()>=self.deadline:raise TimeoutError('sparse Hall DP deadline')
            value=self.add(value,i,thresholds)
        return value
    def visit(self,start,stop,tail,callback):
        if start==stop:return
        if stop-start==1:callback(start,tail);return
        middle=(start+stop)//2;lookahead=self.build(middle,stop,tail)
        self.visit(start,middle,lookahead,callback)
        del lookahead
        self.visit(middle,stop,tail,callback)


def sparse_joint_walk(rest,rare,common,states,durations,residual,cuts,requirements,deadline,stats):
    import numpy as np
    initial=list(zip(*requirements)) if requirements else [()]*len(states)
    oracle=SparseHallOracle(common,residual,cuts,initial,deadline,stats)
    required=np.array([oracle.index[oracle.canonical(tuple(int(v) for v in state))] for state in initial],dtype=np.int64)
    remaining=residual-durations
    def possible(values,needs,table):
        good=(values>=0)&(values<=oracle.upper*oracle.unit)&(values%oracle.unit==0);indices=np.flatnonzero(good)
        for needed in np.unique(needs[indices]):
            part=indices[needs[indices]==needed];goals=values[part]//oracle.unit
            blob=np.frombuffer(table[int(needed)].to_bytes((oracle.upper+8)//8,'little'),dtype=np.uint8)
            good[part]=((blob[goals//8]>>(goals%8))&1)!=0
        return good
    table=oracle.build(0,len(common),oracle.terminal)
    good=possible(remaining,required,table);states=states[good];remaining=remaining[good];required=required[good]
    del table
    if not len(states):return None
    rare_index={t['track_id']:len(rare)-1-i for i,t in enumerate(rare)};chosen=[];cursor=0
    def visit(index,tail):
        nonlocal states,remaining,required,cursor
        while rest[cursor]['track_id']!=common[index]['track_id']:
            t=rest[cursor];include=((states>>rare_index[t['track_id']])&1)!=0
            if np.any(include):states=states[include];remaining=remaining[include];required=required[include]
            cursor+=1
        t=common[index];next_required=oracle.transitions[oracle.marked[index]][required]
        include=possible(remaining-t['duration_ms'],next_required,tail)
        if np.any(include):
            states=states[include];remaining=remaining[include]-t['duration_ms'];required=next_required[include];chosen.append(t)
        cursor+=1
    oracle.visit(0,len(common),oracle.terminal,visit)
    while cursor<len(rest):
        t=rest[cursor];include=((states>>rare_index[t['track_id']])&1)!=0
        if np.any(include):states=states[include];remaining=remaining[include];required=required[include]
        cursor+=1
    assert len(states)==1 and int(remaining[0])==0 and int(required[0])==0
    stats['method']='sparse_hall_exact'
    return chosen+[t for i,t in enumerate(rare) if int(states[0])>>(len(rare)-1-i)&1]


def duration_genre_subset(rest,target,first,genres,deadline,stats):
    """Exact lex DFS with subset sums and a minimum-duration matching bound."""
    from bisect import bisect_left,insort
    from ortools.graph.python import min_cost_flow
    oracle=SumOracle(rest,target,deadline)
    groups=list(genres);limit=len(groups)
    def pattern(t):return sum(1<<j for j,g in enumerate(groups) if g in t['genre_group_codes'])
    patterns=sorted({pattern(t) for t in first+rest}-{0});lookup={mask:i for i,mask in enumerate(patterns)}
    initial=[0]*len(patterns)
    for t in first:
        mask=pattern(t)
        if mask:initial[lookup[mask]]=min(limit,initial[lookup[mask]]+1)
    positions=[[] for _ in patterns];durations=[[] for _ in patterns];kind=[]
    for i,t in enumerate(rest):
        mask=pattern(t);j=lookup.get(mask,-1);kind.append(j)
        if j>=0:positions[j].append(i);durations[j].append(t['duration_ms'])
    cheapest=[]
    for values in durations:
        suffix=[None]*(len(values)+1);suffix[-1]=();current=[]
        for i in range(len(values)-1,-1,-1):
            insort(current,values[i]);current=current[:limit];suffix[i]=tuple(current)
        cheapest.append(suffix)
    @lru_cache(maxsize=32768)
    def lower(index,signature):
        solver=min_cost_flow.SimpleMinCostFlow();source=0;start=1+limit;sink=start+len(patterns)
        for j in range(limit):
            solver.add_arc_with_capacity_and_unit_cost(source,1+j,1,0)
            for k,mask in enumerate(patterns):
                if mask>>j&1:solver.add_arc_with_capacity_and_unit_cost(1+j,start+k,1,0)
        for k,mask in enumerate(patterns):
            if signature[k]:solver.add_arc_with_capacity_and_unit_cost(start+k,sink,signature[k],0)
            for value in cheapest[k][bisect_left(positions[k],index)]:
                solver.add_arc_with_capacity_and_unit_cost(start+k,sink,1,value)
        solver.set_node_supply(source,limit);solver.set_node_supply(sink,-limit)
        status=solver.solve()
        if status==solver.OPTIMAL:return solver.optimal_cost()
        if status==solver.INFEASIBLE:return float('inf')
        return -1
    stack=[(0,target,(),tuple(initial))];visited=set();nodes=0;cuts=0
    while stack:
        if monotonic()>=deadline:
            stats.update(duration_genre_nodes=nodes,duration_genre_prunes=cuts);return False,None
        index,remaining,chosen,signature=stack.pop();nodes+=1
        state=(index,remaining,signature)
        if state in visited:continue
        visited.add(state)
        if not oracle.possible_from(index,remaining):continue
        minimum=lower(index,signature)
        if minimum<0:return False,None
        if minimum>remaining:cuts+=1;continue
        if minimum==0:
            extra=oracle.subset_from(index,remaining)
            assert extra is not None
            stats.update(duration_genre_nodes=nodes,duration_genre_prunes=cuts,method='genre_duration_matching_exact')
            return True,[rest[i] for i in chosen]+extra
        if index==len(rest) or remaining==0:continue
        stack.append((index+1,remaining,chosen,signature))
        if rest[index]['duration_ms']<=remaining:
            next_signature=list(signature);j=kind[index]
            if j>=0:next_signature[j]=min(limit,next_signature[j]+1)
            stack.append((index+1,remaining-rest[index]['duration_ms'],chosen+(index,),tuple(next_signature)))
    stats.update(duration_genre_nodes=nodes,duration_genre_prunes=cuts)
    return True,None


def contract_fixed_genres(first,genres,representatives):
    """Remove components already matched using disjoint fixed-track slots."""
    graph={g:{g} for g in genres}
    for t in first:
        members=set(genres).intersection(t['genre_group_codes'])
        for g in members:graph[g]|=members
    unseen=set(genres);remaining=set()
    while unseen:
        todo=[unseen.pop()];component=set()
        while todo:
            g=todo.pop();component.add(g);adjacent=graph[g]&unseen;unseen-=adjacent;todo.extend(adjacent)
        if representatives(first,sorted(component)) is None:remaining|=component
    return sorted(remaining)


def eager_hall_cuts(first,rare,common,genres,states,deadline,stats):
    """Contract fixed tracks and discard implied Hall inequalities before DP."""
    import numpy as np
    if len(genres)>17:return None
    start=monotonic();fixed_masks=[];rare_masks=[];common_masks=[]
    for g in genres:
        fixed_masks.append(sum(1<<i for i,t in enumerate(first) if g in t['genre_group_codes']))
        rare_masks.append(sum(1<<(len(rare)-1-i) for i,t in enumerate(rare) if g in t['genre_group_codes']))
        common_masks.append(sum(1<<i for i,t in enumerate(common) if g in t['genre_group_codes']))
    unions=[0]*(1<<len(genres));candidates=[]
    for mask in range(1,len(unions)):
        bit=mask&-mask;j=bit.bit_length()-1;unions[mask]=unions[mask^bit]|fixed_masks[j]
        need=mask.bit_count()-unions[mask].bit_count()
        if need<=0:continue
        rare_mask=common_mask=0
        for j,g in enumerate(genres):
            if mask>>j&1:rare_mask|=rare_masks[j];common_mask|=common_masks[j]
        candidates.append((common_mask.bit_count(),mask,need,rare_mask,common_mask))
        if mask%1024==0 and monotonic()>=deadline:raise TimeoutError('Hall projection deadline')
    candidates.sort();kept=[]
    lut=np.array([i.bit_count() for i in range(65536)],dtype=np.uint8)
    for _,mask,need,rare_mask,common_mask in candidates:
        bits=states&rare_mask;population=np.zeros(len(states),dtype=np.int16)
        for shift in range(0,len(rare),16):population+=lut[(bits>>shift)&65535]
        required=np.maximum(0,need-population)
        if not int(required.max()):continue
        implied=False
        for a in kept:
            if a[1]&~common_mask==0 and np.all(a[2]>=required):implied=True;break
        if not implied:
            for i,a in enumerate(kept):
                for c in kept[:i]:
                    if not a[1]&c[1] and (a[1]|c[1])&~common_mask==0 and np.all(a[2]+c[2]>=required):
                        implied=True;break
                if implied:break
        if implied:continue
        kept=[a for a in kept if not (common_mask&~a[1]==0 and np.all(required>=a[2]))]
        kept.append((mask,common_mask,required))
        if len(kept)>32:return None
        if monotonic()>=deadline:raise TimeoutError('Hall projection reduction deadline')
    cells=1
    for mask,common_mask,required in kept:cells*=int(required.max())+1
    stats.update(eager_hall_candidates=len(candidates),eager_hall_cuts=len(kept),eager_hall_cells=cells,eager_hall_seconds=monotonic()-start)
    return [{g for j,g in enumerate(genres) if mask>>j&1} for mask,_,_ in kept]


def lex_genre_subset(ordered,target,genres,deadline,representatives,stats,initial_forced=(),rare_cap=22,
                     score_costs=None,score_budget=0,hint_positive=()):
    import numpy as np
    costs=score_costs or {}
    necessary=necessary_genre_tracks(ordered,genres,representatives)
    if necessary is None:return None
    forced=set(initial_forced)|necessary
    if len(ordered)>400 or hint_positive:
        start=monotonic();positive=set(hint_positive)
        hint_face=[t for t in ordered if not costs.get(t['track_id'],0) or t['track_id'] in positive]
        if forced<= {t['track_id'] for t in hint_face}:
            hint=prefix_witness(hint_face,target,genres,forced|positive,min(deadline,start+1.5),representatives)
        else:hint=None
        stats['prefix_hint_seconds']=monotonic()-start
        if hint is not None:
            assert sum(costs.get(t['track_id'],0) for t in hint)==score_budget
            ids={t['track_id'] for t in hint};count=0
            for t in ordered:
                if t['track_id'] in forced:continue
                if t['track_id'] not in ids:break
                forced.add(t['track_id']);count+=1
            stats['prefix_hint_fixed']=count
    first=[t for t in ordered if t['track_id'] in forced]
    rest=[t for t in ordered if t['track_id'] not in forced]
    all_genres=list(genres);genres=contract_fixed_genres(first,genres,representatives)
    stats['fixed_satisfied_genres']=len(all_genres)-len(genres)
    residual=target-sum(t['duration_ms'] for t in first)
    loss_left=score_budget-sum(costs.get(t['track_id'],0) for t in first)
    if residual<0 or loss_left<0:return None
    counts=Counter(g for t in ordered for g in t['genre_group_codes'])
    restricted={g for g in genres if counts[g]<=4}
    always_rare={t['track_id'] for t in rest if costs.get(t['track_id'],0)>0}
    def rare_for(groups):return [t for t in rest if t['track_id'] in always_rare or groups.intersection(t['genre_group_codes'])]
    if len(ordered)>400:
        for g in sorted(genres,key=lambda g:counts[g]):
            if len(rare_for(restricted|{g}))<=rare_cap:restricted.add(g)
    cuts=[]
    outside=[g for g in genres if g not in restricted and not any(g in t['genre_group_codes'] for t in first)]
    if outside and len(ordered)>400:cuts=[{min(outside,key=lambda g:counts[g])}]
    lut=np.array([i.bit_count() for i in range(65536)],dtype=np.uint8)
    for attempt in range(2*len(genres)+1):
        if monotonic()>=deadline:raise TimeoutError('genre joint states deadline')
        rare=rare_for(restricted);rare_ids={t['track_id'] for t in rare};common=[t for t in rest if t['track_id'] not in rare_ids]
        if len(rare)>60:
            stats['rare_state_gate']=len(rare)
            return None
        stats.update({'active_join_attempt':attempt+1,'active_rare_tracks':len(rare),'active_common_tracks':len(common),
                      'active_genre_phase':'joint_states','active_hall_cuts':[sorted(cut) for cut in cuts]})
        # Keep only nonnegative loss/duration states which can still fit. This
        # avoids allocating 2**n arrays for tied positive genre alternatives.
        durations=np.zeros(1,dtype=np.int64);losses=np.zeros(1,dtype=np.int64);states=np.zeros(1,dtype=np.int64)
        for bit,t in enumerate(reversed(rare)):
            include=(losses+costs.get(t['track_id'],0)<=loss_left)&(durations+t['duration_ms']<=residual)
            if len(states)+int(include.sum())>2097152:
                stats['rare_state_gate']=len(states)+int(include.sum());return None
            durations=np.concatenate((durations,durations[include]+t['duration_ms']))
            losses=np.concatenate((losses,losses[include]+costs.get(t['track_id'],0)))
            states=np.concatenate((states,states[include]|(1<<bit)))
            if monotonic()>=deadline:raise TimeoutError('sparse genre states deadline')
        size=len(states);valid=losses==loss_left
        neighbors={g:{g} for g in restricted}
        for t in first+rare:
            connected=restricted.intersection(t['genre_group_codes'])
            for g in connected:neighbors[g]|=connected
        unseen=set(restricted);components=[]
        while unseen:
            todo=[unseen.pop()];component=set()
            while todo:
                g=todo.pop();component.add(g);adjacent=neighbors[g]&unseen;unseen-=adjacent;todo.extend(adjacent)
            components.append(sorted(component))
        for component in components:
            if len(component)>10:return None
            for mask in range(1,1<<len(component)):
                subset={g for j,g in enumerate(component) if mask>>j&1}
                needed=len(subset)-sum(bool(subset.intersection(t['genre_group_codes'])) for t in first)
                if needed<=0:continue
                union=sum(1<<(len(rare)-1-j) for j,t in enumerate(rare) if subset.intersection(t['genre_group_codes']))
                bits=states&union;population=np.zeros(len(bits),dtype=np.int16)
                for shift in range(0,len(rare),16):population+=lut[(bits>>shift)&65535]
                valid &= population>=needed
        states=states[valid];durations=durations[valid]
        if not len(states):return None
        if not common:
            states=states[durations==residual]
            if not len(states):return None
            chosen=first+[t for j,t in enumerate(rare) if int(states.max())>>(len(rare)-1-j)&1]
        else:
            if attempt==0 and len(ordered)>400:
                projected=eager_hall_cuts(first,rare,common,genres,states,deadline,stats)
                if projected is not None:cuts=projected
                elif loss_left==0 and not any(costs.get(t['track_id'],0) for t in rest):
                    handled,answer=duration_genre_subset(rest,residual,first,genres,min(deadline,monotonic()+5),stats)
                    if handled:
                        if answer is None:return None
                        chosen=first+answer
                        assert representatives(chosen,all_genres) is not None
                        stats['genre_partition_certified']=True
                        return chosen
            requirements=[];active=[];maxima=[]
            for cut in cuts:
                union=sum(1<<(len(rare)-1-j) for j,t in enumerate(rare) if cut.intersection(t['genre_group_codes']))
                bits=states&union;population=np.zeros(len(bits),dtype=np.int16)
                for shift in range(0,len(rare),16):population+=lut[(bits>>shift)&65535]
                needed=np.maximum(0,len(cut)-sum(bool(cut.intersection(t['genre_group_codes'])) for t in first)-population)
                maximum=int(needed.max())
                if maximum:requirements.append(needed);active.append(cut);maxima.append(maximum)
            cuts=active
            stats['active_genre_phase']='joint_dp'
            cells=1
            for maximum in maxima:cells*=maximum+1
            if cells>64:
                answer=sparse_joint_walk(rest,rare,common,states,durations,residual,cuts,requirements,deadline,stats)
                if answer is None:return None
                chosen=first+answer
                if representatives(chosen,all_genres) is None:return None
                stats['genre_partition_certified']=True
                return chosen
            oracle=MultiCountSumOracle(common,residual,deadline,cuts,maxima)
            required=np.zeros(len(states),dtype=np.int64)
            for needed,stride in zip(requirements,oracle.strides):required+=needed*stride
            remaining=residual-durations
            def possible(index,values,needs):
                good=(values>=0)&(values<=oracle.upper*oracle.unit)&(values%oracle.unit==0);indices=np.flatnonzero(good)
                for needed in np.unique(needs[indices]):
                    part=indices[needs[indices]==needed];goals=values[part]//oracle.unit
                    blob=np.frombuffer(oracle.suffix_at(index,int(needed)).to_bytes((oracle.upper+8)//8,'little'),dtype=np.uint8)
                    good[part]=((blob[goals//8]>>(goals%8))&1)!=0
                return good
            good=possible(0,remaining,required);states=states[good];remaining=remaining[good];required=required[good]
            if not len(states):return None
            common_index=0;rare_index={t['track_id']:len(rare)-1-j for j,t in enumerate(rare)};chosen_common=[]
            stats['active_genre_phase']='joint_lex'
            for t in rest:
                if monotonic()>=deadline:raise TimeoutError('genre joint lex deadline')
                if t['track_id'] in rare_index:include=((states>>rare_index[t['track_id']])&1)!=0;next_required=required
                else:
                    common_index+=1;mark=sum(1<<j for j,cut in enumerate(cuts) if cut.intersection(t['genre_group_codes']))
                    next_required=oracle.transitions[mark,required]
                    include=possible(common_index,remaining-t['duration_ms'],next_required)
                if np.any(include):
                    states=states[include];remaining=remaining[include];required=next_required[include]
                    if t['track_id'] not in rare_index:chosen_common.append(t);remaining-=t['duration_ms']
            assert len(states)==1 and int(remaining[0])==0 and int(required[0])==0
            chosen=first+chosen_common+[t for j,t in enumerate(rare) if int(states[0])>>(len(rare)-1-j)&1]
        missing=deficient_genres(chosen,genres)
        stats.update({'genre_join_attempts':attempt+1,'rare_tracks':len(rare),'rare_states':size,
                      'restricted_genres':sorted(restricted),'hall_cuts':[sorted(cut) for cut in cuts]})
        if not missing:
            assert sum(costs.get(t['track_id'],0) for t in chosen)==score_budget
            assert representatives(chosen,all_genres) is not None
            stats['genre_partition_certified']=True
            return chosen
        if missing<=restricted or missing in cuts:return None
        if len(rare_for(restricted|missing))<=rare_cap:restricted|=missing
        else:cuts.append(missing)
    return None


def genre_bound_fill(ordered,target,genres,deadline,representatives,stats):
    """Exact min-cost matching bounds the score lost to mandatory genre coverage."""
    if not genres or not ordered:return None
    maximum=max(Fraction(t['scores']['S'] or 0) for t in ordered)
    losses=[(maximum-Fraction(t['scores']['S'] or 0))*t['duration_ms'] for t in ordered]
    denominator=lcm(*(v.denominator for v in losses))
    costs=[int(v*denominator) for v in losses]
    common=gcd(*costs) or 1;costs=[value//common for value in costs]
    if sum(costs)>=2**61:return None
    if any(costs):
        from ortools.graph.python import min_cost_flow
        def matching(blocked=None):
            if monotonic()>=deadline:raise TimeoutError('genre bound deadline')
            solver=min_cost_flow.SimpleMinCostFlow()
            source=0;start=1+len(genres);sink=start+len(ordered)
            links=[]
            for j,genre in enumerate(genres):
                solver.add_arc_with_capacity_and_unit_cost(source,1+j,1,0)
                for i,t in enumerate(ordered):
                    if t['track_id']==blocked or genre not in t['genre_group_codes']:continue
                    arc=solver.add_arc_with_capacity_and_unit_cost(1+j,start+i,1,0)
                    links.append((arc,i))
            for i,t in enumerate(ordered):
                if t['track_id']!=blocked:solver.add_arc_with_capacity_and_unit_cost(start+i,sink,1,costs[i])
            solver.set_node_supply(source,len(genres));solver.set_node_supply(sink,-len(genres))
            status=solver.solve()
            if status==solver.INFEASIBLE:return float('inf'),[]
            if status!=solver.OPTIMAL:return None,[]
            return solver.optimal_cost(),[i for arc,i in links if solver.flow(arc)]
        cost,assigned=matching()
        if cost is None or cost==float('inf'):return None
        positive={i for i in assigned if costs[i]>0}
        # Every positive-cost chosen track must occur in every minimum matching;
        # otherwise this shortcut declines rather than choose an arbitrary tie.
        forced_positive=set()
        for i in positive:
            alternative,_=matching(ordered[i]['track_id'])
            if alternative is None:return None
            if alternative>cost:forced_positive.add(i)
    else:cost=0;positive=set();forced_positive=set()
    forced_cost=sum(costs[i] for i in forced_positive)
    optional={i for i,value in enumerate(costs) if value>0 and value<=cost-forced_cost and i not in forced_positive}
    first=[t for i,t in enumerate(ordered) if i in forced_positive]
    zeros=[t for i,t in enumerate(ordered) if costs[i]==0]
    residual=target-sum(t['duration_ms'] for t in first)
    if sum(t['duration_ms'] for t in zeros)<residual:return None
    face=[t for i,t in enumerate(ordered) if costs[i]==0 or i in forced_positive or i in optional]
    if representatives(face,genres) is None:return None
    stats.update({'positive_genre_tracks':len(first),'optional_positive_tracks':len(optional),'matching_loss':str(Fraction(cost*common,denominator)),
                  'optimal_face_tracks':len(face)})
    try:result=lex_genre_subset(face,target,genres,deadline,representatives,stats,
                               [t['track_id'] for t in first],score_costs={t['track_id']:costs[i] for i,t in enumerate(ordered)},
                               score_budget=cost,hint_positive=[ordered[i]['track_id'] for i in positive])
    except OverflowError:
        stats['genre_memory_gate']=True
        return None
    if result is None:return None
    quality=sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in result)
    bound=maximum*target-Fraction(cost*common,denominator)
    assert quality==bound and sum(t['duration_ms'] for t in result)==target
    stats.update({'method':'genre_matching_bitset','certified':True,'quality':str(quality),
                  'positive_genre_tracks':len(first),'matching_loss':str(Fraction(cost*common,denominator))})
    return sorted(result,key=lambda t:(-Fraction(t['scores']['S'] or 0),t['track_id']))


def early_reduced_exact(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,stats):
    """Try cheap exact reductions before constructing a larger hint neighborhood."""
    local={};args=modular_reduce(candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,local)
    candidates,scores,pivot,upper,lower,forced_in,free,hint,target,deadline,local=args
    result=plateau_reduced_exact(*args) if free else None
    if result is not None:pass
    elif not free:
        result=[candidates[i] for i in forced_in];local['method']='early_modular_exact'
    elif len(free)<=40:
        weights=[scores[i]*candidates[i]['duration_ms'] for i in free];denominator=lcm(*(v.denominator for v in weights))
        answer=numpy_subset([candidates[i] for i in free],[int(v*denominator) for v in weights],target-sum(candidates[i]['duration_ms'] for i in forced_in),deadline)
        assert answer is not None
        result=[candidates[i] for i in forced_in]+answer[0];local['method']='early_array_exact'
    if result is not None:
        assert sum(t['duration_ms'] for t in result)==target and sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in result)>=lower
        stats.update(local);stats['early_bound_width']=36
    return result


class CoreDeclined(Exception):pass


def genre_dual_bound(ordered,target,genres,deadline,stats):
    """LP proposes dual prices; exact fractions certify the resulting bound.

    A distinct representative matching implies sum(bonus_i*x_i)>=sum(price_g).
    Consequently quality <= pivot*T-sum(prices)+sum(max(0,reduced_i)).
    This inequality is valid for any nonnegative prices, independently of the
    floating point LP status or numerical accuracy.
    """
    from ortools.linear_solver import pywraplp
    start=monotonic();lp=pywraplp.Solver.CreateSolver('GLOP')
    if lp is None or start>=deadline:return None
    lp.SetNumThreads(1);lp.SetTimeLimit(max(1,int(min(.5,deadline-start)*1000)))
    xs=[lp.NumVar(0,1,f'x{i}') for i in range(len(ordered))]
    time=lp.Constraint(target,target);rows={g:lp.Constraint(1,1) for g in genres}
    scores=[Fraction(t['scores']['S'] or 0) for t in ordered]
    for i,t in enumerate(ordered):
        time.SetCoefficient(xs[i],t['duration_ms'])
        capacity=lp.Constraint(-lp.infinity(),0);capacity.SetCoefficient(xs[i],-1)
        for g in set(genres).intersection(t['genre_group_codes']):
            y=lp.NumVar(0,lp.infinity(),f'r{i}_{g}')
            rows[g].SetCoefficient(y,1);capacity.SetCoefficient(y,1)
        lp.Objective().SetCoefficient(xs[i],float(scores[i]*t['duration_ms']))
    lp.Objective().SetMaximization();status=lp.Solve()
    if status!=lp.OPTIMAL:return None
    pivot=Fraction(str(time.dual_value())).limit_denominator(1000000)
    grid=lcm(pivot.denominator,*(v.denominator for v in scores))
    prices={g:max(Fraction(0),Fraction(round(-row.dual_value()*grid),grid)) for g,row in rows.items()}
    reduced=[(score-pivot)*t['duration_ms']+max([Fraction(0)]+[prices[g] for g in set(genres).intersection(t['genre_group_codes'])]) for score,t in zip(scores,ordered)]
    upper=pivot*target-sum(prices.values())+sum(max(Fraction(0),v) for v in reduced)
    stats.update(dual_seconds=monotonic()-start,dual_upper=str(upper),dual_prunes=0)
    return upper,{t['track_id']:v for t,v in zip(ordered,reduced)},[x.solution_value() for x in xs],prices


def improve_genre_witness(ordered,target,genres,share,dual,witness,deadline,representatives,stats):
    """Exchange a genre representative, retaining an exactly feasible hint."""
    upper,reduced=dual[:2];prices=dual[3]
    weights=[Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in ordered]
    denominator=lcm(*(v.denominator for v in weights));coefficients=[int(v*denominator) for v in weights]
    unit=gcd(*coefficients) or 1;coefficients=[v//unit for v in coefficients]
    by_id={t['track_id']:i for i,t in enumerate(ordered)}
    ranking=sorted(range(len(ordered)),key=lambda i:abs(reduced[ordered[i]['track_id']]))
    best=witness;quality=sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in best);initial=quality;trials=0
    assignment=representatives(best,genres)
    if assignment is None:return best
    for genre in sorted(genres,key=lambda g:-prices.get(g,0)):
        if prices.get(genre,0)<=0 or quality==upper:continue
        old=assignment[genre];required=set(assignment.values())-{old}
        choices=[i for i in ranking if genre in ordered[i]['genre_group_codes'] and ordered[i]['track_id'] not in required and ordered[i]['track_id']!=old][:3]
        for replacement in choices:
            if monotonic()>=deadline:break
            if ordered[replacement]['track_id'] in required:continue
            first=required|{ordered[replacement]['track_id']};selected={by_id[t['track_id']] for t in best if t['track_id']!=old}|{replacement}
            sequence=sorted([i for i in ranking if ordered[i]['track_id'] not in first][:36]);free=set(sequence);fixed=selected-free
            residual=target-sum(ordered[i]['duration_ms'] for i in fixed)
            if residual<0 or residual>sum(ordered[i]['duration_ms'] for i in sequence):continue
            trials+=1
            try:answer=numpy_subset([ordered[i] for i in sequence],[coefficients[i] for i in sequence],residual,deadline)
            except TimeoutError:break
            if answer is None:continue
            chosen=[ordered[i] for i in fixed]+answer[0]
            selected_ms=sum(t['duration_ms'] for t in chosen if set(genres).intersection(t['genre_group_codes']))
            if 100*selected_ms<share*target:continue
            assert sum(t['duration_ms'] for t in chosen)==target
            if representatives(chosen,genres) is None:continue
            candidate=sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in chosen)
            if candidate>quality:
                best=chosen;quality=candidate;assignment=representatives(best,genres)
                old=assignment[genre];required=set(assignment.values())-{old}
    stats.update(genre_hint_exchanges=trials,genre_hint_exchange_gain=str(quality-initial))
    return best


def genre_initial_witness(ordered,target,genres,share,dual,deadline,representatives,stats):
    """A feasible native solve supplies a lower bound, never an optimum claim."""
    if dual is None:return None
    upper,reduced,values=dual[:3];preferred={i for i,t in enumerate(ordered) if reduced[t['track_id']]>0}
    ranking=sorted(range(len(ordered)),key=lambda i:abs(reduced[ordered[i]['track_id']]))
    weights=[Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in ordered]
    denominator=lcm(*(v.denominator for v in weights));coefficients=[int(v*denominator) for v in weights]
    common=gcd(*coefficients) or 1;coefficients=[v//common for v in coefficients]
    if sum(abs(v) for v in coefficients)>=2**62:return None
    start=monotonic()
    integral={i for i,v in enumerate(values) if v>=1-1e-7}
    assignment=representatives([t for i,t in enumerate(ordered) if i in integral],genres)
    if assignment is not None:
        best_hint=None;best_hint_quality=None;best_width=None
        required={assignment[g] for g in genres if dual[3].get(g,0)>0}
        eligible=[i for i in ranking if ordered[i]['track_id'] not in required]
        for width in (36,40,44):
            free=set(eligible[:width]);fixed=integral-free;sequence=sorted(free)
            residual=target-sum(ordered[i]['duration_ms'] for i in fixed)
            if residual<0 or residual>sum(ordered[i]['duration_ms'] for i in sequence):continue
            try:answer=numpy_subset([ordered[i] for i in sequence],[coefficients[i] for i in sequence],residual,min(deadline,start+2))
            except TimeoutError:answer=None;break
            if answer is None:continue
            chosen=[t for i,t in enumerate(ordered) if i in fixed]+answer[0]
            selected_ms=sum(t['duration_ms'] for t in chosen if set(genres).intersection(t['genre_group_codes']))
            if share*target>100*selected_ms:continue
            assert sum(t['duration_ms'] for t in chosen)==target
            if representatives(chosen,genres) is None:continue
            quality=sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in chosen)
            if best_hint_quality is None or quality>best_hint_quality:best_hint=chosen;best_hint_quality=quality;best_width=width
            if sum(abs(v)<=upper-quality for v in reduced.values())<=44:break
        if best_hint is not None:
            best_hint_quality=sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in best_hint)
            stats.update(genre_hint_method='lp_neighborhood_exact',genre_hint_seconds=monotonic()-start,
                         genre_hint_quality=str(best_hint_quality),genre_hint_width=best_width)
            return best_hint
    for width in (44,72,128):
        if monotonic()>=deadline:return None
        free=set(ranking[:width]);fixed=preferred-free;allowed=fixed|free
        model=cp_model.CpModel();xs={i:model.NewBoolVar(f'w{i}') for i in free}
        fixed_duration=sum(ordered[i]['duration_ms'] for i in fixed)
        model.Add(sum(xs[i]*ordered[i]['duration_ms'] for i in free)==target-fixed_duration)
        reps={}
        for g in genres:
            members=[]
            for i in allowed:
                if g in ordered[i]['genre_group_codes']:
                    y=model.NewBoolVar(f'r{i}_{g}');reps.setdefault(i,[]).append(y);members.append(y)
            model.Add(sum(members)==1)
        for i,members in reps.items():model.Add(sum(members)<=(1 if i in fixed else xs[i]))
        if share:
            selected=lambda i:bool(set(genres).intersection(ordered[i]['genre_group_codes']))
            model.Add(100*(sum(ordered[i]['duration_ms'] for i in fixed if selected(i))+sum(xs[i]*ordered[i]['duration_ms'] for i in free if selected(i)))>=share*target)
        model.Maximize(sum(xs[i]*coefficients[i] for i in free))
        for i,x in xs.items():model.AddHint(x,int(values[i]>=.5))
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
        solver.parameters.max_time_in_seconds=max(.001,min(.5,deadline-monotonic()))
        status=solver.Solve(model)
        if status not in (cp_model.FEASIBLE,cp_model.OPTIMAL):continue
        indices=fixed|{i for i,x in xs.items() if solver.Value(x)};chosen=[t for i,t in enumerate(ordered) if i in indices]
        if sum(t['duration_ms'] for t in chosen)!=target or representatives(chosen,genres) is None:continue
        stats.update(genre_hint_seconds=monotonic()-start,genre_hint_quality=str(sum(weights[i] for i in indices)),genre_hint_width=width)
        return chosen
    stats['genre_hint_seconds']=monotonic()-start
    return None


def solve_above_cutoff(ordered,target,cutoff,deadline,stats):
    """Certify the relaxed optimum above a feasible global incumbent, or prune.

    The cutoff need not be feasible in this branch. Empty exhaustive searches
    prove only that the branch cannot match the incumbent's quality.
    """
    if target<0 or sum(t['duration_ms'] for t in ordered)<target:return True,None
    if target==0:return True,[] if cutoff<=0 else None
    scores=[Fraction(t['scores']['S'] or 0) for t in ordered]
    ranking=sorted(range(len(ordered)),key=lambda i:-scores[i]);left=target
    for i in ranking:
        left-=min(left,ordered[i]['duration_ms'])
        if left==0:pivot=scores[i];break
    upper=pivot*target+sum(max(Fraction(0),(score-pivot)*t['duration_ms']) for score,t in zip(scores,ordered))
    gap=upper-cutoff
    if gap<0:stats['cutoff_lp_prune']=True;return True,None
    forced=[];free=[]
    for i,t in enumerate(ordered):
        if abs(scores[i]-pivot)*t['duration_ms']>gap:
            if scores[i]>pivot:forced.append(i)
        else:free.append(i)
    stats.update(cutoff_mode=True,cutoff_upper=str(upper),cutoff_lower=str(cutoff),cutoff_initial_free=len(free))
    args=(ordered,scores,pivot,upper,cutoff,forced,free,set(),target,deadline,stats)
    args=modular_reduce(*args)
    if args is None:return True,None
    forced=args[5];free=args[6];stats['cutoff_final_free']=len(free)
    result=plateau_reduced_exact(*args)
    if result is not None:return True,result
    if stats.get('pivot_proven_empty'):return True,None
    if len(free)<=44:
        weights=[scores[i]*ordered[i]['duration_ms'] for i in free];denominator=lcm(*(v.denominator for v in weights))
        answer=numpy_subset([ordered[i] for i in free],[int(v*denominator) for v in weights],target-sum(ordered[i]['duration_ms'] for i in forced),deadline)
        stats['method']='cutoff_array_exact'
        if answer is None:return True,None
        result=[ordered[i] for i in forced]+answer[0]
        quality=sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in result)
        return True,result if quality>=cutoff else None
    result=finish_bounded_core(*args)
    return result is not None or stats.get('bounded_proven_empty',False),result


def additional_matching_cost(available,forced,genres,costs):
    """Exact minimum extra representative cost, with fixed tracks at zero."""
    from ortools.graph.python import min_cost_flow
    values=[Fraction(0) if t['track_id'] in forced else costs[t['track_id']] for t in available]
    denominator=lcm(*(v.denominator for v in values));coefficients=[int(v*denominator) for v in values]
    common=gcd(*coefficients) or 1;coefficients=[v//common for v in coefficients]
    if sum(coefficients)>=2**61:return None
    flow=min_cost_flow.SimpleMinCostFlow();start=1+len(genres);sink=start+len(available)
    for j,g in enumerate(genres):
        flow.add_arc_with_capacity_and_unit_cost(0,1+j,1,0)
        for i,t in enumerate(available):
            if g in t['genre_group_codes']:flow.add_arc_with_capacity_and_unit_cost(1+j,start+i,1,0)
    for i,cost in enumerate(coefficients):flow.add_arc_with_capacity_and_unit_cost(start+i,sink,1,cost)
    flow.set_node_supply(0,len(genres));flow.set_node_supply(sink,-len(genres));status=flow.solve()
    if status==flow.INFEASIBLE:return float('inf')
    if status!=flow.OPTIMAL:return None
    return Fraction(flow.optimal_cost()*common,denominator)


class SharedDPDeclined(Exception):pass


def shared_genre_dp(ordered,target,genres,dual,witness,deadline,stats):
    import numpy as np
    from collections import defaultdict
    upper,reduced,values,prices=dual
    scores={t['track_id']:Fraction(t['scores']['S'] or 0) for t in ordered}
    bonus={t['track_id']:max([Fraction(0)]+[prices[g] for g in genres if g in t['genre_group_codes']]) for t in ordered}
    first=ordered[0];pivot=scores[first['track_id']]+(bonus[first['track_id']]-reduced[first['track_id']])/first['duration_ms']
    lower=sum(scores[t['track_id']]*t['duration_ms'] for t in witness);gap=upper-lower
    if gap<0:raise AssertionError('invalid dual bound')
    grid=lcm(upper.denominator,lower.denominator,*(v.denominator for v in reduced.values()),*(v.denominator for v in prices.values()),pivot.denominator)
    budget=int(gap*grid);assert Fraction(budget,grid)==gap
    if budget>=2**60:raise SharedDPDeclined('integer range')
    forced={key for key,value in reduced.items() if value>gap}
    blocked={key for key,value in reduced.items() if -value>gap}
    available=[t for t in ordered if t['track_id'] not in blocked]
    necessary=necessary_genre_tracks(available,genres,representatives)
    if necessary is None:raise AssertionError('feasible witness lost')
    forced|=necessary
    common=[t for t in available if not bonus[t['track_id']]]
    rare=[t for t in available if bonus[t['track_id']]]
    if not common or len(rare)>180:raise SharedDPDeclined('unsupported split')
    preferred_ms=sum(t['duration_ms'] for t in common if reduced[t['track_id']]>0)
    constant=0;items=[]
    for t in common:
        key=t['track_id'];value=reduced[key];cost=int(abs(value)*grid)
        if key in forced:
            if value<=0:preferred_ms+=t['duration_ms'];constant+=cost
        else:items.append((cost,-t['duration_ms'] if value>0 else t['duration_ms']))
    remaining_budget=budget-constant
    if remaining_budget<0:raise AssertionError('forced loss')
    def duration_bound(positive):
        zero=sum(abs(d) for c,d in items if c==0 and (d>0)==positive)
        options=sorted(((Fraction(abs(d),c),c,abs(d)) for c,d in items if c>0 and (d>0)==positive),reverse=True)
        left=remaining_budget;result=Fraction(zero)
        for ratio,c,d in options:
            take=min(c,left);result+=take*ratio;left-=take
            if left==0:break
        return result.numerator//result.denominator
    lo=max(-preferred_ms,-duration_bound(False));hi=min(sum(t['duration_ms'] for t in common)-preferred_ms,duration_bound(True))
    size=hi-lo+1
    if size<=0 or size*8*4>160*1024*1024:raise SharedDPDeclined('common DP memory')
    if size*len(items)>300000000:raise SharedDPDeclined('common DP work')
    start=monotonic();infinity=budget+1
    dp=np.full(size,infinity,dtype=np.int64);dp[-lo]=constant
    for cost,duration in sorted(items,reverse=True):
        if monotonic()>=deadline:raise TimeoutError('shared common DP deadline')
        if cost>remaining_budget or abs(duration)>=size:continue
        if duration>0:dp[duration:]=np.minimum(dp[duration:],np.minimum(infinity,dp[:-duration]+cost))
        elif duration<0:dp[:duration]=np.minimum(dp[:duration],np.minimum(infinity,dp[-duration:]+cost))
    stats.update(common_dp_seconds=monotonic()-start,common_tracks=len(common),rare_tracks=len(rare),common_dp_range=[lo,hi],common_dp_bytes=dp.nbytes)
    # Components use only positive-price genres. Distinct representatives in
    # separate components cannot compete for the same rare track.
    active={g for g in genres if prices[g]>0};parent={g:g for g in active}
    def find(g):
        while parent[g]!=g:parent[g]=parent[parent[g]];g=parent[g]
        return g
    memberships={t['track_id']:set(t['genre_group_codes'])&active for t in rare}
    for members in memberships.values():
        group=list(members)
        for g in group[1:]:parent[find(g)]=find(group[0])
    components=defaultdict(set)
    for g in active:components[find(g)].add(g)
    by_id={t['track_id']:t for t in ordered};rare_positions={t['track_id']:i for i,t in enumerate(rare)}
    words=max(1,(len(rare)+63)//64);groups=[];start=monotonic()
    representative=representatives
    work=0
    for component in components.values():
        tracks=[t for t in rare if memberships[t['track_id']]&component]
        fixed=[t for t in tracks if t['track_id'] in forced];optional=[t for t in tracks if t['track_id'] not in forced]
        maximum=min(len(tracks),len(component)+budget//int(min(prices[g] for g in component)*grid))
        count=sum(__import__('math').comb(len(optional),k) for k in range(max(0,len(component)-len(fixed)),maximum-len(fixed)+1))
        if count>2000000:raise SharedDPDeclined('component enumeration cap')
        baseline=sum(max(Fraction(0),reduced[t['track_id']]) for t in tracks)-sum(prices[g] for g in component)
        options=[]
        for amount in range(max(0,len(component)-len(fixed)),maximum-len(fixed)+1):
            for extra in combinations(optional,amount):
                work+=1
                if work%1024==0 and monotonic()>=deadline:raise TimeoutError('genre component deadline')
                chosen=fixed+list(extra)
                cost=(baseline+sum((pivot-scores[t['track_id']])*t['duration_ms'] for t in chosen))*grid
                if cost<0 or cost>budget:continue
                if representative(chosen,sorted(component)) is None:continue
                assert cost.denominator==1
                mask=sum(1<<(len(rare)-1-rare_positions[t['track_id']]) for t in chosen)
                options.append((int(cost),sum(t['duration_ms'] for t in chosen),mask))
        if not options:raise AssertionError(('witness component lost',component))
        groups.append(sorted(options))
    stats['genre_component_options']=sorted(len(group) for group in groups)
    stats['component_seconds']=monotonic()-start
    groups.sort(key=len)
    costs=np.zeros(1,dtype=np.int64);duration=np.zeros(1,dtype=np.int64)
    masks=[np.zeros(1,dtype=np.uint64) for word in range(words)]
    state_limit=min(2000000,(128*1024*1024)//(16+8*words));start=monotonic()
    for position,options in enumerate(groups):
        if monotonic()>=deadline:raise TimeoutError('genre group join deadline')
        reserve=sum(group[0][0] for group in groups[position+1:]);option_cost=np.array([option[0] for option in options],dtype=np.int64)
        counts=np.searchsorted(option_cost,budget-reserve-costs,side='right');count=int(counts.sum())
        if count>state_limit:raise SharedDPDeclined('genre product state cap '+str(count))
        new_cost=[];new_duration=[];new_masks=[[] for word in range(words)]
        for option_index,(cost,delta,mask) in enumerate(options):
            if option_index%16==0 and monotonic()>=deadline:raise TimeoutError('genre group options deadline')
            include=costs<=budget-reserve-cost
            if not np.any(include):continue
            new_cost.append(costs[include]+cost);new_duration.append(duration[include]+delta)
            for word in range(words):new_masks[word].append(masks[word][include]|np.uint64((mask>>(64*word))&((1<<64)-1)))
        costs=np.concatenate(new_cost);duration=np.concatenate(new_duration);masks=[np.concatenate(parts) for parts in new_masks]
    stats.update(genre_product_states=len(costs),genre_join_seconds=monotonic()-start)
    wanted=target-duration;delta=wanted-preferred_ms;valid=(delta>=lo)&(delta<=hi)
    indices=np.flatnonzero(valid);common_cost=dp[delta[indices]-lo];loss=costs[indices]+common_cost
    valid=loss<=budget;indices=indices[valid];loss=loss[valid]
    if not len(indices):raise AssertionError('feasible witness absent from exact DP')
    minimum=int(loss.min());indices=indices[loss==minimum]
    stats.update(shared_min_loss=str(Fraction(minimum,grid)),optimal_rare_states=len(indices),shared_quality=str(upper-Fraction(minimum,grid)))
    global_bits={t['track_id']:1<<(len(ordered)-1-i) for i,t in enumerate(ordered)}
    common_upper=sum(max(Fraction(0),reduced[t['track_id']]) for t in common)
    fixed_common=[t for t in common if t['track_id'] in forced]
    free_common=[t for t in common if t['track_id'] not in forced]
    fixed_ms=sum(t['duration_ms'] for t in fixed_common)
    fixed_quality=sum(scores[t['track_id']]*t['duration_ms'] for t in fixed_common)
    answers={};best=None;best_mask=-1
    for index in indices:
        if monotonic()>=deadline:raise TimeoutError('shared DP tie deadline')
        goal=int(wanted[index]);cost=int(dp[int(delta[index]-lo)])
        quality=pivot*goal+common_upper-Fraction(cost,grid)
        if goal not in answers:
            local={};handled,answer=solve_above_cutoff(free_common,goal-fixed_ms,quality-fixed_quality,deadline,local)
            if not handled or answer is None:raise SharedDPDeclined('common optimal face reconstruction')
            answer=fixed_common+answer
            assert sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in answer)==quality
            answers[goal]=answer
        mask=sum(int(masks[word][index])<<(64*word) for word in range(words))
        chosen=answers[goal]+[t for i,t in enumerate(rare) if mask>>(len(rare)-1-i)&1]
        if representative(chosen,genres) is None:raise SharedDPDeclined('unpriced genre on optimal face')
        assert sum(t['duration_ms'] for t in chosen)==target
        assert sum(Fraction(t['scores']['S'] or 0)*t['duration_ms'] for t in chosen)==upper-Fraction(minimum,grid)
        full_mask=sum(global_bits[t['track_id']] for t in chosen)
        if full_mask>best_mask:best=chosen;best_mask=full_mask
    stats.update(method='shared_genre_common_dp',certified=True,quality=str(upper-Fraction(minimum,grid)))
    return best


def genre_branch_core(ordered,target,genres,share,deadline,engine,representatives,stats):
    """Exact partition of scarce genre choices, with conditional quality bounds."""
    by_id={t['track_id']:t for t in ordered}
    ranked=sorted(ordered,key=lambda t:-Fraction(t['scores']['S'] or 0))
    scores={t['track_id']:Fraction(t['scores']['S'] or 0) for t in ordered}
    bits={t['track_id']:1<<(len(ordered)-1-i) for i,t in enumerate(ordered)}
    maximum=max(scores.values());best=None;best_quality=None;best_mask=-1
    dual=genre_dual_bound(ordered,target,genres,deadline,stats) if len(ordered)>400 else None
    witness=genre_initial_witness(ordered,target,genres,share,dual,deadline,representatives,stats) if len(genres)>2 else None
    if witness is not None:
        best=witness;best_quality=sum(scores[t['track_id']]*t['duration_ms'] for t in witness);best_mask=sum(bits[t['track_id']] for t in witness)
    if witness is not None and len(ordered)>400 and len(genres)>=8 and (not share or all(set(genres).intersection(t['genre_group_codes']) for t in ordered)):
        try:shared=shared_genre_dp(ordered,target,genres,dual,witness,deadline,stats)
        except SharedDPDeclined as error:stats['shared_dp_declined']=str(error)
        else:return sorted(shared,key=lambda t:(-scores[t['track_id']],t['track_id']))
    matching_cache={}
    def branch(forced,excluded,parent_quality=None,parent_mask=None):
        nonlocal best,best_quality,best_mask
        if monotonic()>=deadline:raise TimeoutError('genre quality partition deadline')
        stats['genre_quality_nodes']=stats.get('genre_quality_nodes',0)+1
        if best_quality is not None and parent_quality is not None and (parent_quality<best_quality or (parent_quality==best_quality and parent_mask<=best_mask)):
            stats['inherited_prunes']=stats.get('inherited_prunes',0)+1;return
        next_quality=parent_quality;next_mask=parent_mask
        if dual is not None and best_quality is not None:
            dual_upper,reduced=dual[:2]
            penalty=sum(max(Fraction(0),-reduced[key]) for key in forced)+sum(max(Fraction(0),reduced[key]) for key in excluded)
            remaining_gap=dual_upper-best_quality-penalty
            if remaining_gap<0:stats['dual_prunes']+=1;return
            forced=forced|{key for key,value in reduced.items() if key not in excluded and value>remaining_gap}
            excluded=excluded|{key for key,value in reduced.items() if key not in forced and -value>remaining_gap}
            stats['dual_free_remaining']=len(ordered)-len(forced)-len(excluded)
        available=[t for t in ordered if t['track_id'] not in excluded]
        matching_key=frozenset(excluded)
        if matching_key not in matching_cache:
            started=monotonic();matching_cache[matching_key]=necessary_genre_tracks(available,genres,representatives)
            stats['matching_seconds']=stats.get('matching_seconds',0)+monotonic()-started
        else:stats['matching_cache_hits']=stats.get('matching_cache_hits',0)+1
        necessary=matching_cache[matching_key]
        if necessary is None:return
        forced=forced|necessary
        fixed=[by_id[key] for key in forced]
        residual=target-sum(t['duration_ms'] for t in fixed)
        if residual<0:return
        constant=sum(scores[t['track_id']]*t['duration_ms'] for t in fixed)
        remaining=[t for t in available if t['track_id'] not in forced]
        if sum(t['duration_ms'] for t in remaining)<residual:return
        upper=constant;left=residual;conditional_pivot=maximum
        for t in ranked:
            if t['track_id'] in excluded or t['track_id'] in forced:continue
            take=min(left,t['duration_ms']);upper+=take*scores[t['track_id']];left-=take
            if left==0:conditional_pivot=scores[t['track_id']];break
        if best_quality is not None and len(genres)>2:
            started=monotonic()
            duration=additional_matching_cost(available,forced,genres,{t['track_id']:Fraction(t['duration_ms']) for t in available})
            if duration is not None and duration>residual:
                stats['duration_prunes']=stats.get('duration_prunes',0)+1;return
            penalty=additional_matching_cost(available,forced,genres,{t['track_id']:max(Fraction(0),(conditional_pivot-scores[t['track_id']])*t['duration_ms']) for t in available})
            if penalty is not None:upper-=penalty
            stats['flow_bound_seconds']=stats.get('flow_bound_seconds',0)+monotonic()-started
        if dual is not None:
            dual_upper,reduced=dual[:2]
            conditional=dual_upper-sum(max(Fraction(0),-reduced[key]) for key in forced)-sum(max(Fraction(0),reduced[key]) for key in excluded)
            upper=min(upper,conditional)
        if best_quality is not None and upper<best_quality:
            stats['dual_prunes']=stats.get('dual_prunes',0)+1;return
        present={g for t in fixed for g in t['genre_group_codes']}
        scarce=[]
        for genre in genres:
            if genre in present:continue
            members=[t['track_id'] for t in remaining if genre in t['genre_group_codes']]
            if len(members)<=4:scarce.append(members)
        if scarce:
            cut=min(scarce,key=len)
        else:
            trial={};started=monotonic()
            if residual==0:relaxed=[]
            else:
                handled=False
                if best_quality is not None:
                    handled,relaxed=solve_above_cutoff(remaining,residual,best_quality-constant,deadline,trial)
                    if handled and relaxed is None:
                        stats['cutoff_prunes']=stats.get('cutoff_prunes',0)+1
                        trial['conditional_seconds']=monotonic()-started
                        stats.setdefault('genre_quality_trials',[]).append(trial);return
                if not handled:relaxed=pivot_fill(remaining,residual,deadline,trial)
                if relaxed is None:relaxed=engine.solve_core(remaining,residual,deadline,trial)
            trial['conditional_seconds']=monotonic()-started
            stats.setdefault('genre_quality_trials',[]).append(trial)
            if relaxed is None:
                handled,witness=exact_bits(remaining,residual,deadline)
                if handled and witness is None:return
                raise CoreDeclined('conditional optimum not certified')
            chosen=fixed+relaxed
            quality=sum(scores[t['track_id']]*t['duration_ms'] for t in chosen)
            mask=sum(bits[t['track_id']] for t in chosen)
            next_quality=quality;next_mask=mask
            if best_quality is not None and (quality<best_quality or (quality==best_quality and mask<=best_mask)):return
            deficient=deficient_genres(chosen,genres)
            selected_ms=sum(t['duration_ms'] for t in chosen if set(genres).intersection(t['genre_group_codes']))
            if not deficient and 100*selected_ms>=share*target:
                best=chosen;best_quality=quality;best_mask=mask
                stats['best_known_quality']=str(quality);stats['best_updates']=stats.get('best_updates',0)+1;return
            if not deficient:raise CoreDeclined('share constraint needs original model')
            chosen_ids={t['track_id'] for t in chosen}
            cut=[t['track_id'] for t in available if t['track_id'] not in chosen_ids and deficient.intersection(t['genre_group_codes'])]
        best_ids={t['track_id'] for t in best} if best is not None else set()
        cut.sort(key=lambda key:(key not in best_ids,(max(Fraction(0),-dual[1][key]) if dual is not None and best_quality is not None else (maximum-scores[key])*by_id[key]['duration_ms']),
                                 (maximum-scores[key])*by_id[key]['duration_ms'],key))
        prior=set(excluded)
        for key in cut:
            branch(forced|{key},prior,next_quality,next_mask)
            prior=prior|{key}
    branch(set(),set())
    if best is not None:stats.update({'method':'genre_quality_partition','certified':True,'quality':str(best_quality)})
    return sorted(best,key=lambda t:(-scores[t['track_id']],t['track_id'])) if best is not None else None


def finish_reduced_cp(*args):
        args=modular_reduce(*args)
        if not args[6]:
            result=[args[0][i] for i in args[5]]
            assert sum(t['duration_ms'] for t in result)==args[8]
            args[-1]['method']='modular_exact'
            return result
        result=plateau_reduced_exact(*args)
        if result is None:result=finish_bounded_core(*args)
        if result is None and len(args[0])>400 and len(args[6])>100 and not args[-1].get('strong_modular_done'):
            args[-1]['strong_modular_done']=True
            reduced=strong_modular_reduce(*args)
            if len(reduced[6])<len(args[6]):return finish_reduced_cp(*reduced)
        if result is None and len(args[0])>400 and len(args[6])>100 and not args[-1].get('quality_probe_done'):
            improved=improve_incumbent(*args)
            if improved is not None:return finish_reduced_cp(*improved)
        return result if result is not None else _finish_reduced_cp(*args)


class _CoreEngine:
    """Stateless adapter shared by exact genre partition subproblems."""
    solve_core = staticmethod(solve_core)


_ENGINE = _CoreEngine()


def _reduced_or_fallback(candidates, deadline, selected_genres, min_selected_share, seed, fallback):
    ordered = sorted(candidates, key=lambda t: (
        hashlib.sha256((seed + '\0' + t['track_id']).encode()).digest() if seed else b'', t['track_id']))
    stats = {}
    result = None
    if len(ordered) <= 400:
        try:
            result = solve_core(ordered, policy.TARGET, deadline, stats)
        except TimeoutError:
            stats['timed_out'] = True
    if result is not None:
        selected = set(selected_genres)
        selected_ms = sum(t['duration_ms'] for t in result if selected.intersection(t['genre_group_codes']))
        if not selected_genres or (representatives(result, selected_genres) is not None and
                                  100 * selected_ms >= min_selected_share * sum(t['duration_ms'] for t in result)):
            return result
    if monotonic() >= deadline or (stats.get('cp_calls') and stats.get('last_status') in ('UNKNOWN', 'FEASIBLE')):
        raise DomainError('SEARCH_INCOMPLETE', '정해진 시간 안에 탐색을 완료하지 못했어요.', 503)
    return fallback(candidates, deadline, selected_genres, min_selected_share, seed)


def solve_window(candidates, deadline, selected_genres=(), min_selected_share=0, seed='', *, fallback):
    """Try certified exact shortcuts, then the unchanged-duration fallback.

    The basic-query speed refinement remains deferred. All stages receive the
    same absolute deadline, genre requirements, share and deterministic seed.
    """
    ordered = sorted(candidates, key=lambda t: (
        hashlib.sha256((seed + '\0' + t['track_id']).encode()).digest() if seed else b'', t['track_id']))
    def original():
        return _reduced_or_fallback(candidates, deadline, selected_genres, min_selected_share, seed, fallback)
    stats = {}
    weights = [Fraction(t['scores']['S'] or 0) * t['duration_ms'] for t in ordered]
    denominator = lcm(*(w.denominator for w in weights))
    if sum(abs(int(w * denominator)) for w in weights) >= 2**62:
        return original()
    forced = necessary_genre_tracks(ordered, selected_genres, representatives) if selected_genres else set()
    if forced is None:
        return None
    first = [t for t in ordered if t['track_id'] in forced]
    remainder = [t for t in ordered if t['track_id'] not in forced]
    try:
        result = genre_bound_fill(ordered, policy.TARGET, selected_genres, deadline, representatives, stats) if len(selected_genres) > 1 else None
        if result is None:
            result = pivot_fill(remainder, policy.TARGET - sum(t['duration_ms'] for t in first), deadline, stats)
        else:
            first = []
        if result is not None:
            result = sorted(first + result, key=lambda t: (-Fraction(t['scores']['S'] or 0), t['track_id']))
            selected = set(selected_genres)
            selected_ms = sum(t['duration_ms'] for t in result if selected.intersection(t['genre_group_codes']))
            if not selected_genres or (representatives(result, selected_genres) is not None and
                                      100 * selected_ms >= min_selected_share * sum(t['duration_ms'] for t in result)):
                return result
        if selected_genres:
            try:
                result = genre_branch_core(ordered, policy.TARGET, selected_genres, min_selected_share,
                                           deadline, _ENGINE, representatives, {})
            except CoreDeclined:
                result = None
            if result is not None:
                return result
    except TimeoutError:
        raise DomainError('SEARCH_INCOMPLETE', '정해진 시간 안에 탐색을 완료하지 못했어요.', 503) from None
    return original()

\n