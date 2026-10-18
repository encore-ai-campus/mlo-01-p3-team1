import os
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.sessions.models import Session


class Command(BaseCommand):
    help = '최초 ADMIN 발급 또는 명시 회수. 기존 비밀번호/권한을 덮어쓰지 않습니다.'

    def add_arguments(self,parser):
        parser.add_argument('username')
        parser.add_argument('--permissions',nargs='*',choices=['manage_ads','manage_music','view_feedback'],default=[])
        action=parser.add_mutually_exclusive_group()
        action.add_argument('--revoke',action='store_true')
        action.add_argument('--reset-password',action='store_true')

    def handle(self,*args,**options):
        User=get_user_model()
        with transaction.atomic():
            user=User.objects.select_for_update().filter(username=options['username']).first()
            if options['revoke']:
                if user is None:raise CommandError('account_not_found')
                user.is_active=False;user.save(update_fields=['is_active'])
                for session in Session.objects.iterator():
                    if session.get_decoded().get('_auth_user_id')==str(user.pk):session.delete()
                self.stdout.write('admin_revoked');return
            if options['reset_password']:
                if user is None or not user.is_active or not user.is_staff:raise CommandError('active_admin_required')
                password=os.environ.get('BOOTSTRAP_ADMIN_PASSWORD','')
                if not password:raise CommandError('new_password_required')
                try:validate_password(password,user)
                except ValidationError:raise CommandError('password_policy_failed') from None
                user.set_password(password);user.save(update_fields=['password'])
                for session in Session.objects.iterator():
                    if session.get_decoded().get('_auth_user_id')==str(user.pk):session.delete()
                self.stdout.write('admin_password_reset_sessions_revoked');return
            if user is not None:raise CommandError('existing_account_unchanged')
            password=os.environ.get('BOOTSTRAP_ADMIN_PASSWORD','')
            if not password or not options['permissions']:raise CommandError('password_and_explicit_permissions_required')
            user=User(username=options['username'],is_staff=True,is_active=True)
            try:validate_password(password,user)
            except ValidationError:raise CommandError('password_policy_failed') from None
            permissions=list(Permission.objects.filter(content_type__app_label='common',codename__in=options['permissions']))
            if len(permissions)!=len(set(options['permissions'])):raise CommandError('run_migrations_first')
            user.set_password(password);user.save();user.user_permissions.set(permissions)
        self.stdout.write('admin_created')
