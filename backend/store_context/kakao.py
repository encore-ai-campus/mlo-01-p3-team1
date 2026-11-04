"""카카오 Local의 제한된 카테고리 검색 결과 집계. 전체 상권 통계가 아님."""
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


CATEGORY_LABELS = {
    'CE7': '카페', 'CT1': '문화시설', 'SC4': '학교',
    'SW8': '지하철역', 'AT4': '관광명소', 'FD6': '음식점',
}
DEFAULT_CATEGORIES = ('CE7', 'CT1', 'SC4', 'SW8', 'AT4')
ENDPOINT = 'https://dapi.kakao.com/v2/local/search/category.json'


class ProviderFailure(Exception):
    """사용자 출력에 URL·키·서버 응답 본문을 포함하지 않는 오류."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderFailure('redirect_rejected')


def number(value, low, high):
    if isinstance(value, bool):
        raise ValueError('invalid_number')
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError('invalid_number')
    return result


def distance_m(lon, lat, other_lon, other_lat):
    a, b = math.radians(lat), math.radians(other_lat)
    delta_lon = math.radians(other_lon - lon)
    delta_lat = b - a
    h = math.sin(delta_lat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(delta_lon / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


class KakaoPlaces:
    def __init__(self, api_key='', *, max_pages=3, timeout=5, transport=None):
        if type(max_pages) is not int or not 1 <= max_pages <= 3:
            raise ValueError('invalid_page_budget')
        self.api_key = api_key
        self.max_pages = max_pages
        self.timeout = number(timeout, 0.1, 15)
        self.transport = transport or self._request

    def _request(self, params):
        request = Request(ENDPOINT + '?' + urlencode(params),
                          headers={'Authorization': 'KakaoAK ' + self.api_key})
        try:
            with build_opener(NoRedirect()).open(request, timeout=self.timeout) as response:
                body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ProviderFailure('response_too_large')
            return json.loads(body)
        except HTTPError as error:
            if error.code == 429:
                raise ProviderFailure('rate_limited') from None
            if error.code in (401, 403):
                raise ProviderFailure('credentials_rejected') from None
            raise ProviderFailure('upstream_http_error') from None
        except (URLError, TimeoutError, OSError):
            raise ProviderFailure('upstream_unavailable') from None
        except (ValueError, UnicodeError):
            raise ProviderFailure('invalid_response') from None

    def search(self, longitude, latitude, radius_m, categories=DEFAULT_CATEGORIES):
        longitude = number(longitude, -180, 180)
        latitude = number(latitude, -90, 90)
        if type(radius_m) is not int or not 50 <= radius_m <= 2000:
            raise ValueError('radius_m_must_be_50_to_2000')
        categories = tuple(categories)
        if not categories or len(set(categories)) != len(categories) or any(c not in CATEGORY_LABELS for c in categories):
            raise ValueError('unsupported_categories')
        scope = dict(radius_m=radius_m, categories=list(categories),
                     coverage='queried_categories_only', population_complete=False)
        if not self.api_key:
            return dict(status='unavailable', data=None, warnings=['provider_not_configured'], scope=scope)
        places, warnings, failures, completed = {}, [], {}, []
        category_warnings = {category: [] for category in categories}
        category_pages = {category: 0 for category in categories}
        def warn(category, reason):
            category_warnings[category].append(reason)
            warnings.append(reason)
        successful_pages = 0
        for category in categories:
            seen_ids = set()
            for page in range(1, self.max_pages + 1):
                try:
                    response = self.transport(dict(category_group_code=category, x=longitude, y=latitude,
                                                   radius=radius_m, page=page, size=15, sort='distance'))
                    meta, documents = response['meta'], response['documents']
                    if not isinstance(documents, list) or len(documents) > 15 or type(meta['is_end']) is not bool:
                        raise ValueError('invalid_page')
                    total, pageable = meta['total_count'], meta['pageable_count']
                    if type(total) is not int or type(pageable) is not int or not 0 <= pageable <= total:
                        raise ValueError('invalid_counts')
                except ProviderFailure as error:
                    failures[category] = str(error)
                    break
                except (KeyError, TypeError, ValueError):
                    failures[category] = 'invalid_response'
                    break
                successful_pages += 1
                category_pages[category] += 1
                new_ids = 0
                for document in documents:
                    try:
                        identifier = document['id']
                        if not isinstance(identifier, str) or not identifier.isdecimal() or len(identifier) > 32:
                            raise ValueError('invalid_id')
                        if document['category_group_code'] != category:
                            raise ValueError('wrong_category')
                        lon = number(document['x'], -180, 180)
                        lat = number(document['y'], -90, 90)
                        measured = distance_m(longitude, latitude, lon, lat)
                        if measured > radius_m + 1:
                            raise ValueError('outside_radius')
                        if document.get('distance') not in (None, ''):
                            number(document['distance'], 0, 20000)
                    except (KeyError, TypeError, ValueError):
                        warn(category, 'invalid_place_excluded')
                        continue
                    if identifier not in seen_ids:
                        new_ids += 1
                        seen_ids.add(identifier)
                    existing = places.get(identifier)
                    if existing and existing['category'] != category:
                        warn(category, 'conflicting_place_category')
                        continue
                    # 전화번호·주소·업체명 등 외부 자유문구는 추천 입력에 전달하지 않음.
                    places.setdefault(identifier, dict(category=category, distance_m=measured))
                if total > pageable:
                    warn(category, 'provider_result_limit')
                if meta['is_end']:
                    if len(seen_ids) < pageable:
                        warn(category, 'incomplete_page_results')
                    completed.append(category)
                    break
                if not new_ids:
                    warn(category, 'pagination_no_progress')
                    break
                if page == self.max_pages:
                    warn(category, 'page_budget_reached')
        if failures:
            warnings.extend('category_' + code + '_' + reason for code, reason in failures.items())
        complete = len(completed) == len(categories) and not warnings
        if not successful_pages:
            return dict(status='unavailable', data=None, warnings=sorted(set(warnings)), scope=scope)
        total_found = len(places)
        groups = []
        for category in categories:
            distances = [p['distance_m'] for p in places.values() if p['category'] == category]
            category_complete = category in completed and not category_warnings[category] and category not in failures
            category_status = ('ok' if distances else 'empty') if category_complete else (
                'partial' if category_pages[category] else 'unavailable')
            groups.append(dict(category=category, label=CATEGORY_LABELS[category],
                               status=category_status, complete=category_complete,
                               count=len(distances) if category_complete else None,
                               observed_count=len(distances) if category_pages[category] else None,
                               fraction=(len(distances) / total_found if total_found else 0) if complete else None,
                               nearest_distance_m=round(min(distances), 1) if distances else None))
        return dict(status=('empty' if not total_found else 'ok') if complete else 'partial',
                    data=dict(unique_places=total_found, categories=groups,
                              search_results_complete=complete, successful_pages=successful_pages),
                    warnings=sorted(set(warnings)), scope=scope)

