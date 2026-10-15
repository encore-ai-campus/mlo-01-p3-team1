"""Adopted 2026-10-14 music policy. No optional theme heuristics or shortening."""
from fractions import Fraction
from .errors import require

POLICY = 'WEATHER_MUSIC_V4_CYCLE_FIXED'
MAPPING = 'GENRE_THEME_V3_CRITERIA_FIRST'
OPTIONS = 'options-music-v3'
DURATION_POLICY = 'phase3-duration-20261014.2'
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
PROFILES = {
    'CLEAR': (5,8,0,60,True), 'CLOUDY': (3,6,20,80,False), 'OVERCAST': (2,5,40,100,False),
    'RAIN': (2,4,60,100,False), 'MIXED': (2,4,50,100,False), 'SNOW': (1,4,60,100,True),
}
SPEEDS = {'slow','medium','fast','fastest'}


def groups(raw_genres):
    return sorted(code for code, (_, labels) in GENRES.items() if set(raw_genres) & set(labels.split()))


def profile(pty, sky):
    require(type(pty) is int and pty in range(8), 'FORECAST_UNAVAILABLE', '강수 예보를 확인할 수 없어요.', 503)
    if pty == 0:
        require(type(sky) is int and sky in (1,3,4), 'FORECAST_UNAVAILABLE', '하늘 예보를 확인할 수 없어요.', 503)
        return {1:'CLEAR',3:'CLOUDY',4:'OVERCAST'}[sky]
    return {1:'RAIN',2:'MIXED',3:'SNOW',4:'RAIN',5:'RAIN',6:'MIXED',7:'SNOW'}[pty]


def initial_speeds(tempo, segments):
    if tempo == 'slow':
        return ['slow']
    # Preserve phenomena, not just the score profile: PTY1 and PTY4 differ here.
    phenomena = {(s['pty'], s['sky'] if s['pty'] == 0 else None) for s in segments}
    require(len(phenomena) == 1, 'POLICY_NOT_READY', '혼합 예보의 최초 빠르기 기준을 준비하고 있어요.', 503)
    pty, _ = next(iter(phenomena))
    if tempo == 'fast':
        return ['fast'] if pty in (1,3) else ['fast','fastest']
    return ['slow','medium'] if pty in (1,3) else sorted(SPEEDS)


def eligible(track, options, allowed_genres, allowed_speeds, excluded):
    reviewed=track.get('instrumental_review_value')
    final=reviewed if type(reviewed) is bool else track.get('instrumental')
    return (track['track_id'] not in excluded and type(track['duration_ms']) is int and track['duration_ms'] > 0
            and type(track.get('energy')) is int and 0 <= track['energy'] <= 10
            and type(track.get('acousticness')) is int and 0 <= track['acousticness'] <= 100
            and bool(set(track['genre_group_codes']) & set(allowed_genres))
            and track.get('speed') in allowed_speeds
            and (options['vocal_option'] != 'instrumental_only' or final is True))


def score(track, options, segments):
    w = Fraction(0)
    for seg in segments:
        el, eu, al, au, mode = PROFILES[profile(seg['pty'], seg['sky'])]
        e = max(0, 100 - 10 * max(el-track['energy'], 0, track['energy']-eu))
        a = max(0, 100 - max(al-track['acousticness'], 0, track['acousticness']-au))
        m = 100 if track['mode'] is not None and track['mode'] == mode else 0
        w += Fraction(seg['overlap_ms'], TARGET) * (Fraction(e,2)+Fraction(9*a,20)+Fraction(m,20))
    matches = []
    if options['tempo_preference'] != 'auto': matches.append(100)
    if options['selected_genre_codes']: matches.append(100)
    if options['selected_theme_codes']:
        matches.append(100 if set(options['selected_theme_codes']) & set(track['theme_codes']) else 0)
    p = Fraction(sum(matches), len(matches)) if matches else None
    return {'W': w, 'P': p, 'S': Fraction(3,4)*w+Fraction(1,4)*p if p is not None else w}
