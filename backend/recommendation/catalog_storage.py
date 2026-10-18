"""Lossless storage for immutable catalogs on small PostgreSQL hosts."""
import base64
import gzip
import hashlib
import json
import zlib

COMPRESSION_THRESHOLD = 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
FORMAT = 'gzip-json-v1'


def serialize(tracks):
    return json.dumps(tracks, ensure_ascii=False, sort_keys=True).encode()


def pack(tracks):
    payload = serialize(tracks)
    if len(payload) > MAX_UNCOMPRESSED_BYTES:
        raise ValueError('catalog_storage_limit_exceeded')
    digest = hashlib.sha256(payload).hexdigest()
    if len(payload) <= COMPRESSION_THRESHOLD:
        return tracks, digest
    return {'format': FORMAT, 'track_count': len(tracks), 'uncompressed_bytes': len(payload),
            'data': base64.b64encode(gzip.compress(payload, compresslevel=6, mtime=0)).decode('ascii')}, digest


def unpack(stored):
    if isinstance(stored, list):
        return stored
    if not isinstance(stored, dict) or stored.get('format') != FORMAT:
        raise ValueError('unknown_catalog_storage_format')
    size, count = stored.get('uncompressed_bytes'), stored.get('track_count')
    if type(size) is not int or not 0 < size <= MAX_UNCOMPRESSED_BYTES or type(count) is not int or count < 1:
        raise ValueError('invalid_catalog_storage_metadata')
    compressed = base64.b64decode(stored['data'], validate=True)
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    payload = decoder.decompress(compressed, size + 1)
    if len(payload) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('invalid_catalog_storage_payload')
    tracks = json.loads(payload)
    if not isinstance(tracks, list) or len(tracks) != count:
        raise ValueError('invalid_catalog_track_count')
    return tracks
