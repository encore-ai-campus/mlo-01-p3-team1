import json
import os
from django.core.management.base import BaseCommand, CommandError
from backend.common.admin_roles import ROLES
from backend.common.sso_provision import provision


class Command(BaseCommand):
    help = '공통 IdP와 서비스 관리자를 함께 발급/변경/회수합니다. --apply 없이는 쓰기나 외부 호출이 없습니다.'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--role', choices=ROLES)
        parser.add_argument('--action', choices=['create','set-role','revoke','reset-password'], default='create')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        action, role = options['action'], options['role']
        if action in ('create','set-role') and not role:
            raise CommandError('one_explicit_role_required')
        if action in ('revoke','reset-password') and role:
            raise CommandError('role_not_allowed_for_this_action')
        if not options['apply']:
            self.stdout.write(json.dumps({'applied':False,'action':action,'role':role,
                'targets':['service','identity_provider'], 'kibana_access':role in ('SUPER_ADMIN','OPS_ADMIN')}))
            return
        try:
            result = provision(options['username'], role, action, os.environ.get('ADMIN_SSO_INITIAL_PASSWORD'))
        except ValueError as error:
            # Only adapter-owned constant codes are allowed; do not echo remote messages.
            safe = str(error)
            if not safe.isidentifier():safe='provision_failed_check_configuration'
            raise CommandError(safe) from None
        except Exception:
            raise CommandError('provision_failed_check_configuration') from None
        self.stdout.write(json.dumps(result))
