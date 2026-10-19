"""One-shot read-only analytics task; systemd invokes this on one Control host."""
import argparse
import fcntl
import json
import os
import secrets
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verify-access', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(Path(args.config).read_text())
    sys.path.insert(0, str(Path(config['application_root']).resolve()))
    from django.conf import settings
    settings.configure(
        SECRET_KEY=secrets.token_urlsafe(32), USE_TZ=True,
        INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes',
                        'backend.common', 'backend.music', 'backend.recommendation'],
        DATABASES={'default': config['database']}, DEFAULT_AUTO_FIELD='django.db.models.BigAutoField')
    import guest_behavior_export as exporter
    if args.verify_access:
        exporter.django_read_only()
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('transaction_read_only'), has_table_privilege(current_user,'common_feedbackevent','INSERT'), has_table_privilege(current_user,'common_feedbackevent','UPDATE'), has_table_privilege(current_user,'common_feedbackevent','DELETE'), has_column_privilege(current_user,'common_feedbackevent','owner_id','SELECT'), has_column_privilege(current_user,'recommendation_catalog','tracks','SELECT')")
            row = cursor.fetchone()
            assert row == ('on', False, False, False, False, False), 'read_only_privilege_check_failed'
        client = exporter.Elasticsearch(config)
        privileges = client.request('POST', '/_security/user/_has_privileges', {'index': [{'names': ['ops-mlo-*'], 'privileges': ['read', 'index']}, {'names': ['analytics-mlo-guest-events-*'], 'privileges': ['index']}]})
        assert privileges['index']['ops-mlo-*'] == {'read': False, 'index': False}
        assert privileges['index']['analytics-mlo-guest-events-*']['index']
        print(json.dumps({'postgres_read_only_verified': True, 'sensitive_columns_denied': True, 'es_writer_isolated': True}))
        return
    lock = Path(config['cursor_path']).with_suffix('.lock')
    with lock.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'skipped': 'another_exporter_running'}))
            return
        print(json.dumps(exporter.run(config, dry_run=args.dry_run), ensure_ascii=False))


if __name__ == '__main__':
    main()
