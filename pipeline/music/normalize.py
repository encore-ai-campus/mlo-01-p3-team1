"""Pure CSV conversion; source is never modified. Use `python -m pipeline.music.normalize`."""
import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

FIELDS = ('track_id track_name artists_id artists_name album_id album_name album_release_date '
          'duration_ms explicit genre energy mode acousticness mood speed main_inst instrumental play_url').split()
RAW_SCHEMA = 'spotify-raw20-v1'
RESULT_SCHEMA = 'music-normalized19-v1'
RAW_FIELDS = set(('track_id artists album_name track_name popularity duration_ms explicit danceability energy key '
                  'loudness mode speechiness acousticness instrumentalness liveness valence tempo time_signature track_genre').split())


def decimal(value):
    if value in ('', None): return None
    n = Decimal(str(value))
    if not n.is_finite(): raise ValueError('non-finite number')
    return n


def boolean(value, nullable=False):
    if nullable and value in ('', None): return None
    if value is True or value == 'True': return True
    if value is False or value == 'False': return False
    raise ValueError('expected boolean True/False')


def integer(value, nullable=False):
    if nullable and value in ('', None): return None
    if type(value) is int: return value
    if isinstance(value, str) and value.isdecimal(): return int(value)
    raise ValueError('expected integer')


def scaled(value, factor):
    n = decimal(value)
    if n is None: return None
    if not 0 <= n <= 1: raise ValueError('source value outside 0..1')
    return int(n*factor)


def speed(tempo, signature):
    n = decimal(tempo)
    if n is None: return None
    if n < 0: raise ValueError('negative tempo')
    if n == 0: return None
    sig = decimal(signature)
    if sig == 3: n /= Decimal('1.5')
    rounded = int(n.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return 'slow' if rounded < 80 else 'medium' if rounded < 110 else 'fast' if rounded < 150 else 'fastest'


def instrumental(raw, review=None, previous=None):
    if review is not None: return review, 'REVIEW'
    n = decimal(raw)
    if n is None: return previous, 'PRESERVED' if previous is not None else 'UNKNOWN'
    if not 0 <= n <= 1: raise ValueError('instrumentalness outside 0..1')
    return (False if n < Decimal('.2') else True if n >= Decimal('.8') else None), 'AUTO'


def normalize(row, schema, existing=None):
    old = existing or {}
    # Review values in ordinary input are never authorized to overwrite confirmed review.
    review = old.get('instrumental_review_value')
    if review is not None and type(review) is not bool: raise ValueError('invalid stored review')
    raw = schema == RAW_SCHEMA
    if schema not in (RAW_SCHEMA, RESULT_SCHEMA): raise ValueError('unknown source_schema_version')
    result = {k: row.get(k) or None for k in FIELDS}
    result['artists_name'] = row.get('artists') if raw else row.get('artists_name')
    result['genre'] = row.get('track_genre') if raw else row.get('genre')
    for k in ['track_id','track_name','artists_name','album_name']:
        if not isinstance(result[k], str) or not result[k].strip(): raise ValueError(f'missing {k}')
    result['duration_ms'] = integer(row.get('duration_ms'))
    if result['duration_ms'] < 0: raise ValueError('negative duration_ms')
    result['explicit'] = boolean(row.get('explicit'))
    if raw:
        for field in ['artists_id','album_id','album_release_date']:
            if result[field] is None: result[field]=old.get(field)
        result['energy'] = scaled(row.get('energy'), 10)
        result['acousticness'] = scaled(row.get('acousticness'), 100)
        for key in ('energy','acousticness','valence'):
            value = decimal(row.get(key))
            if value is not None and not 0 <= value <= 1: raise ValueError(f'{key} outside 0..1')
            result['raw_'+key] = str(value) if value is not None else None
        mode = row.get('mode')
        if type(mode) is bool or mode not in ('0','1',0,1,None,''): raise ValueError('mode must be 0/1')
        result['mode'] = None if mode in (None,'') else str(mode) == '1'
        result['speed'] = speed(row.get('tempo'), row.get('time_signature'))
        result['instrumental'], source = instrumental(row.get('instrumentalness'), review, old.get('instrumental'))
        result['mood'] = old.get('mood')
        result['main_inst'] = old.get('main_inst')
    else:
        for key, upper in [('energy',10),('acousticness',100)]:
            result[key] = integer(row.get(key), True)
            if result[key] is not None and not 0 <= result[key] <= upper: raise ValueError(f'invalid {key}')
        result['mode'] = boolean(row.get('mode'), True)
        if result['speed'] not in (None,'slow','medium','fast','fastest'): raise ValueError('invalid speed')
        result['instrumental'] = review if review is not None else boolean(row.get('instrumental'), True)
        for key in ('energy','acousticness','valence'):
            value = decimal(row.get('raw_'+key)) if 'raw_'+key in row else decimal(old.get('raw_'+key))
            if value is not None and not 0 <= value <= 1: raise ValueError(f'raw_{key} outside 0..1')
            result['raw_'+key] = str(value) if value is not None else None
        source = 'REVIEW' if review is not None else 'PRESERVED'
    ids = result['artists_id']
    if ids is not None and len(ids.split(';')) != len(result['artists_name'].split(';')):
        raise ValueError('artists_id positional mismatch')
    result['genre'] = ';'.join(sorted(set(x.strip() for x in (result['genre'] or '').split(';') if x.strip()))) or None
    result['play_url'] = f"https://open.spotify.com/track/{result['track_id']}"
    return {**result, 'instrumental_review_value':review, 'instrumental_source':source}


def convert(path, schema, existing=None):
    tracks, errors, conflicts, raw_rows = {}, [], set(), {}
    with open(path, newline='', encoding='utf-8-sig') as stream:
        reader=csv.DictReader(stream)
        headers=reader.fieldnames or []
        expected=RAW_FIELDS if schema==RAW_SCHEMA else set(FIELDS)|{'instrumental_review_value'}
        content=[x for x in headers if not (schema==RAW_SCHEMA and x in ('','Unnamed: 0'))]
        optional=set() if schema==RAW_SCHEMA else {'raw_energy','raw_acousticness','raw_valence'}
        if len(set(headers))!=len(headers) or not expected <= set(content) or set(content)-expected-optional:
            raise ValueError('CSV headers do not match source_schema_version; conversion was not started')
        for line, row in enumerate(reader, 2):
            try:
                key = row.get('track_id')
                value = normalize(row, schema, (existing or {}).get(key))
                if key in tracks:
                    keys = [k for k in value if k != 'genre']
                    if any(value[k] != tracks[key][k] for k in keys):
                        conflicts.add(key); raise ValueError('conflicting track_id metadata')
                    value['genre'] = ';'.join(sorted(set((value['genre'] or '').split(';')) | set((tracks[key]['genre'] or '').split(';')))).strip(';') or None
                tracks[key] = value
                raw_rows.setdefault(key, []).append({'line':line, 'raw':row})
            except (ValueError, InvalidOperation) as exc:
                errors.append({'line':line,'track_id':row.get('track_id'),'error':str(exc),'raw':row})
    for key in conflicts: tracks.pop(key, None)
    return {'source_schema_version':schema, 'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'tracks':list(tracks.values()),'source_rows':raw_rows,'errors':errors,'conflicting_track_ids':sorted(conflicts)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source'); parser.add_argument('--schema', choices=[RAW_SCHEMA,RESULT_SCHEMA], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.resolve() == Path(args.source).resolve(): parser.error('source and output must differ')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(convert(args.source,args.schema), ensure_ascii=False), encoding='utf-8')
