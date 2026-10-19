"""Immutable in-process filters for one verified catalog version."""
from collections import Counter
from types import MappingProxyType

from . import policy


WEATHERS = tuple(policy.WEATHER_WEIGHTS) + ('MIXED',)


class CandidateIndex:
    """Compact bitsets for fixed catalog attributes and versioned score gates."""

    def __init__(self, rows):
        self.rows = tuple(rows)
        self.size = len(self.rows)
        byte_count = (self.size + 7) // 8
        keys = (('base', 'instrumental')
                + tuple(f'genre:{code}' for code in policy.GENRES)
                + tuple(f'speed:{code}' for code in sorted(policy.SPEEDS))
                + tuple(f'weather:{code}' for code in WEATHERS))
        buffers = {key: bytearray(byte_count) for key in keys}
        by_id = {}
        options = {'weather_influence_mode': 'OFF', 'vocal_option': 'any'}

        def add(key, index):
            buffers[key][index // 8] |= 1 << (index % 8)

        for index, track in enumerate(self.rows):
            by_id[track['track_id']] = index
            if not policy.eligible(track, options, (), (), set()):
                continue
            add('base', index)
            speed = track.get('speed')
            if speed in policy.SPEEDS:
                add(f'speed:{speed}', index)
            for genre in track['genre_group_codes']:
                if genre in policy.GENRES:
                    add(f'genre:{genre}', index)
            reviewed = track.get('instrumental_review_value')
            instrumental = reviewed if type(reviewed) is bool else track.get('instrumental')
            if instrumental is True:
                add('instrumental', index)

            cache = track.get('score_cache') or {}
            weather_scores = cache.get('weather') or {}
            cache_is_current = cache.get('weather_version') == policy.WEATHER_SCORE_VERSION
            for weather in WEATHERS:
                if weather == 'MIXED':
                    rejected = (cache_is_current and 'RAIN' in weather_scores and 'SNOW' in weather_scores
                                and (weather_scores['RAIN'] is None or weather_scores['SNOW'] is None))
                else:
                    rejected = cache_is_current and weather in weather_scores and weather_scores[weather] is None
                # Missing and old caches remain in the candidate superset. The policy scorer
                # then evaluates their source fields using its existing fallback.
                if not rejected:
                    add(f'weather:{weather}', index)

        masks = {key: int.from_bytes(value, 'little') for key, value in buffers.items()}
        self.masks = MappingProxyType(masks)
        self.by_id = MappingProxyType(by_id)
        self.bitset_bytes = sum(len(value) for value in buffers.values())

    @staticmethod
    def _indices(mask):
        while mask:
            bit = mask & -mask
            yield bit.bit_length() - 1
            mask ^= bit

    def _common_mask(self, options, allowed_genres, allowed_speeds, excluded):
        common = self.masks['base']
        on = options['weather_influence_mode'] == 'ON'
        if on:
            genre_mask = 0
            for code in allowed_genres:
                genre_mask |= self.masks.get(f'genre:{code}', 0)
            speed_mask = 0
            for code in allowed_speeds:
                speed_mask |= self.masks.get(f'speed:{code}', 0)
            common &= genre_mask & speed_mask
        if options['vocal_option'] == 'instrumental_only':
            common &= self.masks['instrumental']
        for track_id in excluded:
            index = self.by_id.get(track_id)
            if index is not None:
                common &= ~(1 << index)
        return common

    def common_count(self, options, allowed_genres, allowed_speeds, excluded):
        """Return the bit-count after the worker's inherited common filters."""
        return self._common_mask(options, allowed_genres, allowed_speeds, excluded).bit_count()

    def candidates(self, options, weather, allowed_genres, allowed_speeds, excluded):
        common = self._common_mask(options, allowed_genres, allowed_speeds, excluded)
        on = options['weather_influence_mode'] == 'ON'

        common_count = common.bit_count()
        common_total_ms = sum(self.rows[index]['duration_ms'] for index in self._indices(common))
        audit = Counter(catalog_count=self.size,
                        common_eligible_count=common_count,
                        common_rejected_count=self.size - common_count,
                        common_eligible_total_ms=common_total_ms,
                        weather_rejected_count=0,
                        off_missing_preference_count=0)

        candidates_mask = common
        if on:
            candidates_mask &= self.masks.get(f'weather:{weather}', 0)
            audit['weather_rejected_count'] = common_count - candidates_mask.bit_count()

        candidates = []
        has_off_preference = (options['selected_theme_codes'] or options['selected_genre_codes']
                              or options['tempo_preference'] != 'auto')
        for index in self._indices(candidates_mask):
            track = self.rows[index]
            scored = policy.score(track, options, weather)
            if scored is None:
                audit['weather_rejected_count'] += 1
                continue
            if not on and scored['P'] is None and has_off_preference:
                audit['off_missing_preference_count'] += 1
                continue
            candidates.append(dict(track, scores=scored))

        audit['candidate_count'] = len(candidates)
        audit['candidate_total_ms'] = sum(track['duration_ms'] for track in candidates)
        return candidates, dict(audit)
