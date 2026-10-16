"""2026-10-16 ON/OFF candidate contract. Scores use exact decimal fractions."""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from .errors import require

POLICY = 'WEATHER_CHOICE_20261016_V2'
WEATHER_SCORE_VERSION = 'WEATHER_SCORE_PROPOSAL_20261016_V2'
OFF_SCORE_VERSION = 'OFF_THEME_GENRE_20261016_V1'
THEME_AFFINITY_VERSION = 'OFF_THEME_AFFINITY_20261016_V1'
MAPPING = 'GENRE_THEME_V4_ON_OFF'
OPTIONS = 'options-music-v4'
DURATION_POLICY = 'phase3-duration-20261016.1'
TARGET, MINIMUM, MAXIMUM = 10_800_000, 10_560_000, 11_040_000
GENRES = {
    'POP': ('팝', 'pop indie-pop power-pop synth-pop cantopop mandopop'),
    'K-POP': ('K-POP', 'k-pop'), 'J-POP': ('J-POP', 'j-pop j-idol j-rock anime'),
    'ROCK': ('록·펑크', 'alt-rock emo grunge hard-rock j-rock psych-rock punk punk-rock rock rock-n-roll rockabilly'),
    'METAL': ('메탈', 'black-metal death-metal grindcore heavy-metal metal metalcore'),
    'ELECTRONIC_DANCE': ('일렉트로닉·댄스', 'breakbeat chicago-house club dance deep-house detroit-techno disco drum-and-bass dubstep edm electro electronic hardstyle house idm minimal-techno progressive-house techno trance trip-hop'),
    'HIPHOP': ('힙합', 'hip-hop'), 'RNB_SOUL_FUNK': ('R&B·소울·펑크', 'r-n-b soul funk'),
    'JAZZ': ('재즈', 'jazz'), 'BLUES': ('블루스', 'blues'),
    'FOLK_COUNTRY': ('포크·컨트리', 'bluegrass country folk honky-tonk singer-songwriter'),
    'OPERA': ('오페라', 'opera'), 'CLASSICAL': ('클래식', 'classical'),
    'NEWAGE': ('뉴에이지', 'new-age'), 'REGGAE_SKA': ('레게·스카', 'dancehall dub reggae ska'),
    'LATIN': ('라틴', 'forro latin latino mpb pagode reggaeton salsa samba sertanejo tango'),
    'AFROBEAT': ('아프로비트', 'afrobeat'), 'GOSPEL': ('가스펠', 'gospel'),
}
THEMES = dict(zip(['CALM','EMOTIONAL','PEACEFUL','DREAMY','ENERGETIC','BRIGHT','PARTY','GROOVY','INTENSE'],
                  ['잔잔한','감성적인','평화로운','몽환적인','활기찬','밝은','파티 분위기','그루브 있는','강렬한']))
SPEEDS = {'slow','medium','fast','fastest'}
WEATHER_WEIGHTS = {
    'CLEAR': (40,25,30,5), 'CLOUDY': (30,35,30,5), 'OVERCAST': (25,40,30,5),
    'RAIN': (30,40,25,5), 'SNOW': (20,45,30,5),
}
# (energy, acousticness, valence, preferred mode, falloff widths, cap)
PATTERNS = {
    'CLEAR': (((.50,.80),(.00,.55),(.55,.90),1,(.35,.40,.35),100),
              ((.50,1),(.00,1),(.50,1),1,(.15,.15,.15),80)),
    'CLOUDY': (((.30,.60),(.25,.75),(.35,.65),0,(.30,.40,.30),100),
               ((.50,1),(.00,1),(.00,.50),0,(.15,.15,.15),80)),
    'OVERCAST': (((.15,.45),(.50,1),(.15,.45),0,(.30,.35,.30),100),
                 ((.00,.50),(.00,.50),(.00,.50),0,(.15,.15,.15),80)),
    'RAIN': (((.10,.40),(.65,1),(.10,.40),0,(.25,.30,.30),100),
             ((.00,.50),(.50,1),(.00,.50),0,(.15,.15,.15),80)),
    'SNOW': (((.05,.35),(.70,1),(.45,.80),1,(.25,.30,.30),100),
             ((.00,.50),(.00,1),(.50,1),1,(.15,.15,.15),80)),
}
# energy interval, mode, speed set, approved service genres.
OFF_THEMES = {
    'CALM': ((0,4),None,('slow','medium'),('JAZZ','NEWAGE','CLASSICAL')),
    'EMOTIONAL': ((0,4),None,('slow','medium'),('RNB_SOUL_FUNK','POP')),
    'PEACEFUL': ((0,5),1,('slow','medium','fast'),('NEWAGE','CLASSICAL','FOLK_COUNTRY','JAZZ')),
    'DREAMY': ((0,5),None,('slow','medium'),('NEWAGE',)),
    'ENERGETIC': ((6,10),None,('fast',),('ELECTRONIC_DANCE','ROCK','HIPHOP','K-POP','J-POP','AFROBEAT')),
    'BRIGHT': (None,1,None,('NEWAGE','POP','K-POP','J-POP')),
    'PARTY': ((6,10),None,('fast','fastest'),('ELECTRONIC_DANCE','HIPHOP','LATIN','AFROBEAT','RNB_SOUL_FUNK')),
    'GROOVY': (None,None,('medium',),('RNB_SOUL_FUNK','AFROBEAT','HIPHOP')),
    'INTENSE': ((5,10),None,None,('METAL','ROCK','ELECTRONIC_DANCE')),
}


def groups(raw_genres):
    return sorted(code for code, (_, labels) in GENRES.items() if set(raw_genres) & set(labels.split()))


def profile(pty, sky):
    require(type(pty) is int and pty in (0,1,2,3,5,6,7), 'FORECAST_UNAVAILABLE', '강수 상태를 확인할 수 없어요.', 503)
    if pty == 0:
        require(type(sky) is int and sky in (1,3,4), 'FORECAST_UNAVAILABLE', '하늘 예보를 확인할 수 없어요.', 503)
        return {1:'CLEAR',3:'CLOUDY',4:'OVERCAST'}[sky]
    return {1:'RAIN',2:'MIXED',3:'SNOW',5:'RAIN',6:'MIXED',7:'SNOW'}[pty]


def initial_speeds(tempo, weather):
    if tempo == 'slow':
        return ['slow']
    if tempo == 'fast':
        return ['fast'] if weather in ('RAIN','SNOW') else ['fast','fastest']
    return ['slow','medium'] if weather in ('RAIN','SNOW') else sorted(SPEEDS)


def eligible(track, options, allowed_genres, allowed_speeds, excluded):
    reviewed=track.get('instrumental_review_value')
    final=reviewed if type(reviewed) is bool else track.get('instrumental')
    return (track['track_id'] not in excluded and type(track['duration_ms']) is int and track['duration_ms'] > 0
            and all(isinstance(track.get(key),str) and bool(track[key].strip()) for key in ('track_name','artists_name','album_name'))
            and bool(track.get('genre_group_codes')) and track.get('speed') in SPEEDS
            and (options['weather_influence_mode']=='OFF' or
                 (bool(set(track['genre_group_codes']) & set(allowed_genres)) and track.get('speed') in allowed_speeds))
            and (options['vocal_option'] != 'instrumental_only' or final is True))


def unit(value):
    try: n = Fraction(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError): return None
    return n if 0 <= n <= 1 else None


def component(value, interval, width):
    low, high = map(lambda x: Fraction(Decimal(str(x))), interval)
    h = Fraction(Decimal(str(width)))
    return 100 * (1 - min(1, max(low-value, 0, value-high) / h))


def weather_fit(track, weather):
    values = [unit(track.get('raw_'+key)) for key in ('energy','acousticness','valence')]
    if any(v is None for v in values): return None
    mode = 0 if track.get('mode') is False else 1 if track.get('mode') is True else None
    def fit_one(code):
        matches=[]; attempts=[]
        for index, (e,a,v,m,half,cap) in enumerate(PATTERNS[code]):
            parts=[component(x,bound,h) for x,bound,h in zip(values,(e,a,v),half)]
            mode_score=100 if mode == m else 0
            weight=WEATHER_WEIGHTS[code]
            w=Fraction(cap,100)*sum(Fraction(c*s,100) for c,s in zip(weight,(*parts,mode_score)))
            attempt={'pattern':code+('_PRIMARY' if index==0 else '_SUPPORT'),
                     'E':parts[0],'A':parts[1],'V':parts[2],'M':mode_score,'W':w,
                     'core_pass':parts[0]>=20 and parts[1]>=20,'threshold_pass':w>=75}
            attempts.append(attempt)
            if not attempt['core_pass']: continue
            matches.append((w,index,parts,mode_score))
        if not matches: return None
        w,index,parts,mode_score=sorted(matches,key=lambda x:(-x[0],x[1]))[0]
        return {'W':w,'pattern':code+('_PRIMARY' if index==0 else '_SUPPORT'),
                'E':parts[0],'A':parts[1],'V':parts[2],'M':mode_score,
                'attempts':attempts} if w>=75 else None
    if weather == 'MIXED':
        rain,snow=fit_one('RAIN'),fit_one('SNOW')
        return {'W':min(rain['W'],snow['W']),'patterns':[rain,snow]} if rain and snow else None
    return fit_one(weather)


def off_preference_details(track, options):
    selected_themes=options['selected_theme_codes']
    direct_genres=options['selected_genre_codes']
    direct_speed=options['tempo_preference']
    if not selected_themes and not direct_genres and direct_speed=='auto': return None
    genres=set(track['genre_group_codes'])
    speed=track.get('speed')
    energy=track.get('energy')
    def measure(theme):
        energy_range, mode, speeds, theme_genres = OFF_THEMES[theme] if theme else (None,None,None,())
        criterion_genres=direct_genres or theme_genres
        criterion_speeds=('slow',) if direct_speed=='slow' else ('fast','fastest') if direct_speed=='fast' else speeds
        parts=[]
        if energy_range:
            if type(energy) is not int or not 0 <= energy <= 10: return None
            parts.append(('E',40,max(0,100-10*max(energy_range[0]-energy,0,energy-energy_range[1]))))
        if criterion_genres: parts.append(('G',40,100 if genres.intersection(criterion_genres) else 0))
        if mode is not None: parts.append(('M',5,100 if track.get('mode') is (mode == 1) else 0))
        if criterion_speeds:
            if speed not in SPEEDS: return None
            order=('slow','medium','fast','fastest')
            distance=min(abs(order.index(speed)-order.index(s)) for s in criterion_speeds)
            parts.append(('T',15,100 if distance==0 else 50 if distance==1 else 0))
        return {'P':Fraction(sum(w*s for _,w,s in parts),sum(w for _,w,_ in parts)),
                'theme':theme,'components':{name:{'weight':w,'score':s} for name,w,s in parts}} if parts else None
    values=[measure(theme) for theme in selected_themes] if selected_themes else [measure(None)]
    return sorted(values,key=lambda item:(-item['P'],item['theme'] or ''))[0] if values and all(v is not None for v in values) else None


def off_preference(track, options):
    evidence=off_preference_details(track,options)
    return evidence['P'] if evidence else None


def _stored_score(track, kind, code, version):
    cache=track.get('score_cache') or {}
    if cache.get(kind+'_version') != version: return False,None
    values=cache.get(kind) or {}
    if code not in values: return False,None
    pair=values[code]
    return True,(Fraction(*pair) if pair is not None else None)


def theme_affinity(track, theme):
    found,value=_stored_score(track,'theme',theme,THEME_AFFINITY_VERSION)
    if found:return value
    evidence=off_preference_details(track,{'selected_theme_codes':[theme],
        'selected_genre_codes':[],'tempo_preference':'auto'})
    return evidence['P'] if evidence else None


def precompute_scores(track):
    """Store exact, versioned source-only scores in an immutable catalog row."""
    def pair(value):return [value.numerator,value.denominator] if value is not None else None
    # Never derive an approved mood or an instrument tag from these estimates.
    weather={}
    for code in WEATHER_WEIGHTS:
        fit=weather_fit(track,code)
        weather[code]=pair(fit['W'] if fit else None)
    themes={code:pair(theme_affinity(track,code)) for code in THEMES}
    return {**track,'score_cache':{'weather_version':WEATHER_SCORE_VERSION,
        'theme_version':THEME_AFFINITY_VERSION,'weather':weather,'theme':themes}}


def score(track, options, weather=None):
    if options['weather_influence_mode']=='OFF':
        themes=options['selected_theme_codes']
        if themes and not options['selected_genre_codes'] and options['tempo_preference']=='auto':
            values=[theme_affinity(track,theme) for theme in themes]
            p=max(values) if values and all(value is not None for value in values) else None
        else:p=off_preference(track,options)
        return {'W':None,'P':p,'S':p}
    if weather == 'MIXED':
        found_rain,rain=_stored_score(track,'weather','RAIN',WEATHER_SCORE_VERSION)
        found_snow,snow=_stored_score(track,'weather','SNOW',WEATHER_SCORE_VERSION)
        if found_rain and found_snow:
            if rain is None or snow is None:return None
            w=min(rain,snow)
        else:
            evidence=weather_fit(track,weather)
            if evidence is None:return None
            w=evidence['W']
    else:
        found,w=_stored_score(track,'weather',weather,WEATHER_SCORE_VERSION)
        if found:
            if w is None:return None
        elif (weather=='CLEAR' and track.get('preview_clear_score_version')==WEATHER_SCORE_VERSION
              and 'preview_clear_w' in track):
            cached=track['preview_clear_w']
            if cached is None:return None
            w=Fraction(*cached)
        else:
            evidence=weather_fit(track,weather)
            if evidence is None: return None
            w=evidence['W']
    matches=[]
    if options['tempo_preference']!='auto': matches.append(100)
    if options['selected_genre_codes']: matches.append(100)
    if options['selected_theme_codes']:
        affinities=[theme_affinity(track,theme) for theme in options['selected_theme_codes']]
        matches.append(max((value for value in affinities if value is not None),default=0))
    p=Fraction(sum(matches),len(matches)) if matches else None
    return {'W':w,'P':p,'S':Fraction(3,4)*w+Fraction(1,4)*p if p is not None else w}
