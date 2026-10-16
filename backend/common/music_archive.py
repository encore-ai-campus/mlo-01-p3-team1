"""음악 CSV 원본의 로컬/S3 이중 보관. 날씨 원천 파일에는 적용하지 않습니다."""
import base64
import hashlib
import re
from pathlib import Path
from django.conf import settings
from backend.recommendation.errors import DomainError, require


def store(path, digest, client=None):
    raw=Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==digest,'SOURCE_CORRUPT','원본 해시를 확인해 주세요.',503)
    bucket=settings.MUSIC_S3_BUCKET;region=settings.MUSIC_S3_REGION;prefix=settings.MUSIC_S3_PREFIX.strip('/')
    if not bucket and settings.LOCAL_DEMO:return {'mode':'LOCAL_DEMO','sha256':digest}
    require(bool(bucket and region and prefix),'POLICY_NOT_READY','음악 S3 보관 설정이 필요합니다.',503)
    require(not any(part in ('.','..') for part in prefix.split('/')))
    key=prefix+'/'+digest+'.csv'
    try:
        if client is None:
            import boto3
            client=boto3.client('s3',region_name=region)
        # No bucket creation or versioning changes here. INF prepares the bucket and IAM.
        if client.get_bucket_versioning(Bucket=bucket).get('Status')!='Enabled':
            raise ValueError('music_bucket_versioning_required')
        from botocore.exceptions import ClientError
        try:
            client.put_object(Bucket=bucket,Key=key,Body=raw,IfNoneMatch='*',
                ChecksumSHA256=base64.b64encode(bytes.fromhex(digest)).decode(),
                Metadata={'sha256':digest},ContentType='text/csv')
        except ClientError as error:
            if error.response.get('ResponseMetadata',{}).get('HTTPStatusCode')!=412:raise
        found=client.head_object(Bucket=bucket,Key=key)
        version=found.get('VersionId')
        if found.get('Metadata',{}).get('sha256')!=digest or found.get('ContentLength')!=len(raw) or not version or version=='null':
            raise ValueError('music_archive_mismatch')
        return {'mode':'S3','bucket':bucket,'region':region,'key':key,'version_id':version,'sha256':digest}
    except Exception:
        raise DomainError('SOURCE_ARCHIVE_UNAVAILABLE','음악 원본 S3 보관 상태를 확인해 주세요.',503) from None


def restore(manifest,target,client=None):
    """명시된 불변 version을 복원하고 SHA-256 검증 후 새 파일만 생성합니다."""
    require(manifest.get('mode')=='S3' and re.fullmatch('[a-f0-9]{64}',manifest.get('sha256','')) is not None)
    path=Path(target)
    require(not path.exists(),'RESTORE_TARGET_EXISTS','복원 대상 파일이 이미 있습니다.',409)
    try:
        if client is None:
            import boto3
            client=boto3.client('s3',region_name=manifest['region'])
        result=client.get_object(Bucket=manifest['bucket'],Key=manifest['key'],VersionId=manifest['version_id'])
        try:raw=result['Body'].read(settings.CSV_UPLOAD_MAX_BYTES+1)
        finally:result['Body'].close()
        if not settings.CSV_UPLOAD_MAX_BYTES or len(raw)>settings.CSV_UPLOAD_MAX_BYTES or hashlib.sha256(raw).hexdigest()!=manifest['sha256']:
            raise ValueError('archive_checksum_invalid')
        with path.open('xb') as output:output.write(raw)
    except Exception:
        raise DomainError('SOURCE_RESTORE_FAILED','음악 원본 복원·무결성 검증에 실패했습니다.',503) from None
