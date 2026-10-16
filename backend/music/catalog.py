import hashlib
import json
from django.db import transaction
from django.conf import settings
from pipeline.music.normalize import FIELDS
from backend.recommendation.errors import require
from backend.recommendation.policy import groups, THEMES, precompute_scores
from backend.recommendation.models import Catalog
from .models import Track


def export_tracks(approved_only=False, source_sha256=None):
    # Prefetch each link once; no genre x mood x instrument cartesian product.
    from django.db.models import Prefetch
    from .models import TrackTag
    links = TrackTag.objects.filter(review_status='approved',tag__is_active=True).select_related('tag')
    query=Track.objects.all()
    if approved_only:
        query=query.filter(review__status='approved')
    if source_sha256 is not None:
        query=query.filter(trackorigin__source_id=source_sha256)
    for track in query.select_related('album').prefetch_related(Prefetch('tracktag_set',queryset=links,to_attr='approved_links')).order_by('track_id'):
        tags = {'genre':[], 'mood':[], 'instrument':[]}
        for link in track.approved_links: tags[link.tag.tag_type].append(link.tag.tag_code)
        row = {key:getattr(track,key,None) for key in FIELDS}
        row.update({key:getattr(track,key) for key in ('raw_energy','raw_acousticness','raw_valence')})
        for key in ['album_id','album_name','album_release_date']: row[key] = getattr(track.album,key)
        row.update(genre=';'.join(sorted(tags['genre'])) or None,
                   mood=';'.join(THEMES.get(x,x) for x in sorted(tags['mood'])) or None,
                   main_inst=';'.join(sorted(tags['instrument'])) or None,
                   genre_group_codes=groups(tags['genre']),theme_codes=sorted(set(tags['mood']) & THEMES.keys()),
                   instrumental_review_value=track.instrumental_review_value,
                   instrumental_source='REVIEW' if track.instrumental_review_value is not None else 'PRESERVED',
                   cover_image_url=None)
        if track.instrumental_review_value is not None: row['instrumental'] = track.instrumental_review_value
        yield row


def publish(version, source_ref, source_sha256, is_test=False):
    """Run after review. Physical source manifest/retention requires C/B/INF integration."""
    require(source_ref and len(source_sha256)==64, message='불변 원본 참조와 해시가 필요합니다.')
    rows = [precompute_scores(row) for row in export_tracks(approved_only=settings.INTEGRATION_ENABLED,
                             source_sha256=source_sha256 if settings.INTEGRATION_ENABLED else None)]
    require(rows, message='발행할 음악이 없습니다.')
    digest = hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with transaction.atomic():
        require(not Catalog.objects.filter(version=version).exists(), message='이미 발행된 버전입니다.',status=409)
        return Catalog.objects.create(version=version,tracks=rows,sha256=digest,source_ref=source_ref,
                                      source_sha256=source_sha256,is_test=is_test,ready=True)
