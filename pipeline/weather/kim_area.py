"""KIM 영역 CSV를 읽고 대표점에 가까운 모델 격자 선택."""
import bisect
import csv
import io
import math


def parse_area(body):
    text = body.decode('utf-8', errors='replace')
    if text.lstrip().startswith('# ERROR:'):
        raise ValueError('kim_data_unavailable')
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ['ix', 'iy', 'lon', 'lat', 'value']:
        raise ValueError('kim_area_header')
    points = []
    seen = set()
    x_coords, y_coords = {}, {}
    for item in reader:
        point = dict(model_ix=int(item['ix']), model_iy=int(item['iy']),
                     lon=float(item['lon']), lat=float(item['lat']), raw=item['value'])
        if not all(math.isfinite(float(point[k])) for k in ('lon', 'lat', 'raw')):
            raise ValueError('kim_nonfinite')
        if not -180 <= point['lon'] <= 180 or not -90 <= point['lat'] <= 90:
            raise ValueError('kim_location')
        key = (point['model_ix'], point['model_iy'])
        if key in seen:
            raise ValueError('kim_area_duplicate')
        seen.add(key)
        ix, iy = key
        if ix in x_coords and x_coords[ix] != point['lon']:
            raise ValueError('kim_area_geometry')
        if iy in y_coords and y_coords[iy] != point['lat']:
            raise ValueError('kim_area_geometry')
        x_coords[ix], y_coords[iy] = point['lon'], point['lat']
        points.append(point)
    if (not points or len(x_coords) * len(y_coords) != len(points)
            or len(set(x_coords.values())) != len(x_coords)
            or len(set(y_coords.values())) != len(y_coords)):
        raise ValueError('kim_area_geometry')
    return points


def distance_km(query, point):
    dy = math.radians(query['lat'] - point['lat'])
    dx = math.radians(query['lon'] - point['lon'])
    a = (math.sin(dy / 2) ** 2 + math.cos(math.radians(query['lat']))
         * math.cos(math.radians(point['lat'])) * math.sin(dx / 2) ** 2)
    return 6371 * 2 * math.asin(min(1, math.sqrt(a)))


def select_grids(points, mapping):
    # KIM 모델 좌표와 서비스 nx/ny를 혼용하지 않음.
    by_position = {(p['lon'], p['lat']): p for p in points}
    xs = sorted({p['lon'] for p in points})
    ys = sorted({p['lat'] for p in points})
    for (nx, ny), query in sorted(mapping.items()):
        if not xs[0] <= query['lon'] <= xs[-1] or not ys[0] <= query['lat'] <= ys[-1]:
            raise ValueError('kim_area_coverage')
        i = bisect.bisect_left(xs, query['lon'])
        j = bisect.bisect_left(ys, query['lat'])
        nearby_x = {max(0, i - 1), min(i, len(xs) - 1)}
        nearby_y = {max(0, j - 1), min(j, len(ys) - 1)}
        candidates = [by_position[(xs[a], ys[b])] for a in nearby_x for b in nearby_y]
        point = min(candidates, key=lambda p: distance_km(query, p))
        yield dict(nx=nx, ny=ny, raw=point['raw'], query_lat=query['lat'],
                   query_lon=query['lon'], source_ix=point['model_ix'],
                   source_iy=point['model_iy'], source_lat=point['lat'],
                   source_lon=point['lon'], spatial_distance_km=round(distance_km(query, point), 4))
