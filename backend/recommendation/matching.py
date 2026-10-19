"""Deterministic distinct-track genre matching shared by all recommendation paths."""


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
