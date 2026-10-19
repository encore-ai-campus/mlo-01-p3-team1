"""Shared Django DB storage for the existing reviewed-video registry contract.

Tables are migration-owned. SQL values remain bound parameters. Row locks retain
the local registry's revision semantics across multiple API processes.
"""
import re
from contextlib import contextmanager
from contextvars import ContextVar
from django.db import connection, transaction, DatabaseError
from .errors import DomainError

review_actor = ContextVar('youtube_review_actor', default='system')

class Row(dict):
    def __getitem__(self,key):
        return tuple(self.values())[key] if isinstance(key,int) else super().__getitem__(key)

class Result:
    def __init__(self,rows,rowcount):self.rows,self.rowcount=rows,rowcount
    def __iter__(self):return iter(self.rows)
    def fetchone(self):return self.rows[0] if self.rows else None

class RegistryConnection:
    def __init__(self,write):self.write=write
    def execute(self,sql,params=()):
        for old,new in [('track_revision','youtube_track_revision'),('mapping','youtube_mapping'),('review_audit','youtube_review_audit')]:
            sql=re.sub(r'\b'+old+r'\b',new,sql)
        sql=sql.replace('?','%s')
        if sql.startswith('INSERT OR IGNORE INTO '):
            sql=sql.replace('INSERT OR IGNORE INTO ','INSERT INTO ',1)+' ON CONFLICT DO NOTHING'
        if self.write and connection.vendor=='postgresql' and sql.startswith('SELECT revision FROM youtube_track_revision WHERE track_id='):
            sql+=' FOR UPDATE'
        with connection.cursor() as cursor:
            cursor.execute(sql,params)
            rows=[Row(zip([c[0] for c in cursor.description],row)) for row in cursor.fetchall()] if cursor.description else []
            return Result(rows,cursor.rowcount)

@contextmanager
def registry_connection(write=False):
    try:
        with transaction.atomic():yield RegistryConnection(write)
    except DatabaseError:
        raise DomainError('REGISTRY_UNAVAILABLE','영상 연결 저장소를 사용할 수 없어요.',503) from None
