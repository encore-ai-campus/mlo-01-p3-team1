"""Explicit initialization for configured replica sets, without local-dev bypasses."""
import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo import MongoClient
from workers.ads_runtime_check import expected_collections, schema_issues


def prepare(database, definitions):
    actual={r['name']:r for r in database.list_collections()}
    # Check every existing validator before making any changes.
    for name,definition in definitions.items():
        if name not in actual:continue
        opts=actual[name].get('options',{})
        if (opts.get('validator')!=definition['validator'] or
                opts.get('validationLevel','strict')!='strict' or opts.get('validationAction','error')!='error'):
            raise CommandError('existing_ads_validator_incompatible')
    for name,definition in definitions.items():
        if name not in actual:
            database.create_collection(name,validator=definition['validator'],validationLevel='strict',validationAction='error')
        for index in definition['indexes']:
            options={k:index[k] for k in ('name','unique','partialFilterExpression','sparse','collation') if k in index}
            database[name].create_index([tuple(pair) for pair in index['keys']],**options)


class Command(BaseCommand):
    help='설정된 광고 MongoDB에 누락 컬렉션/인덱스를 준비합니다. 기존 validator는 덮어쓰지 않습니다.'
    requires_system_checks=[]
    requires_migrations_checks=False

    def add_arguments(self,parser):parser.add_argument('--apply',action='store_true')

    def handle(self,*args,**options):
        definitions=expected_collections()
        if not options['apply']:
            self.stdout.write(json.dumps({'applied':False,'collections':sorted(definitions)}));return
        if not settings.ADS_MONGODB_URI or not settings.ADS_MONGODB_DATABASE:
            raise CommandError('ads_mongo_configuration_required')
        try:
            with MongoClient(settings.ADS_MONGODB_URI,serverSelectionTimeoutMS=5000,tz_aware=True) as client:
                hello=client.admin.command('hello')
                if not hello.get('setName') or not hello.get('isWritablePrimary'):
                    raise CommandError('ads_replica_set_primary_required')
                database=client[settings.ADS_MONGODB_DATABASE]
                prepare(database,definitions)
                if schema_issues(database):raise CommandError('ads_schema_check_failed')
            self.stdout.write(json.dumps({'applied':True,'schema_verified':True}))
        except CommandError:raise
        except Exception as error:
            raise CommandError('ads_preparation_failed:'+type(error).__name__) from None
