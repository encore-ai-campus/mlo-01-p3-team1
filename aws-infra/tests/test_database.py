"""Native DB guard/auth/TLS/package isolation tests. No server or AWS operations."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'lib'), str(ROOT/'bin'), str(ROOT/'installer')]
import project, install, database_config as dc, database as db


def configuration():
    c = project.load(ROOT/'config/project.example.json')
    c['generation'] = 'db-test'
    c['network_reviewed'] = True
    c['ami_id'] = 'ami-0123456789abcdef0'
    c['az_ids'] = {'a':'apne2-az1','b':'apne2-az2','c':'apne2-az3'}
    return c


def inventory(c):
    nodes = []
    for a in c['accounts']:
        for n in a['nodes']:
            i = len(nodes)+1
            nodes.append({**n, 'profile':a['profile'], 'account_id':a['account_id'], 'az_id':c['az_ids'][n['az_slot']],
                          'instance_id':f'i-{i:017x}', 'data_volume_id':f'vol-{i:017x}', 'ssm_online':True, 'state':'running'})
    return {'environment':'aws','project':c['project'],'environment_name':c['environment'],'generation':c['generation'],'nodes':nodes}


class DatabaseSecurity(unittest.TestCase):
    def setUp(self):
        self.c = configuration()
        self.env = {k: 'test_'+'A'*40 for k in dc.SECRET_KEYS}
        self.versions = json.loads((ROOT/'installer/databases.versions.json').read_text())
        self.nodes = inventory(self.c)['nodes']

    def runtime(self, kind):
        return dc.runtime(self.c, next(n for n in self.nodes if n['role']==kind), self.env, self.versions)

    def test_node_credentials_are_isolated(self):
        pg = self.runtime('postgresql')
        mongo = self.runtime('mongodb')
        self.assertIn('POSTGRES_APP_PASSWORD', pg['env'])
        self.assertNotIn('MONGO_ADMIN_PASSWORD', pg['env'])
        self.assertNotIn('POSTGRES_APP_PASSWORD', mongo['env'])
        for kind, role in [('postgresql','control'),('mongodb','advertising')]:
            value = dc.client(self.c, self.env, kind)
            self.assertNotIn('admin_user', value)
            self.assertNotIn('MONGO_ADMIN_PASSWORD', value)
            self.assertTrue(dc.client_environment({'node':{'role':role}, 'database_client':value}))

    def test_postgres_rejects_plaintext_and_remote_admin(self):
        value = self.runtime('postgresql')
        files = dc.postgres_files(value)
        self.assertIn('ssl = on', files['postgresql.conf'])
        self.assertIn("password_encryption = 'scram-sha-256'", files['postgresql.conf'])
        self.assertIn('host all all 0.0.0.0/0 reject', files['pg_hba.conf'])
        self.assertEqual(files['pg_hba.conf'].count('hostssl'),3)
        self.assertNotIn(' trust', files['pg_hba.conf'])
        self.assertNotIn('hostssl all postgres', files['pg_hba.conf'])

    def test_mongodb_auth_enabled_before_private_binding(self):
        value = self.runtime('mongodb')
        first = json.loads(dc.mongo_config(value, loopback_only=True))
        final = json.loads(dc.mongo_config(value))
        self.assertEqual(first['net']['bindIp'],'127.0.0.1')
        for rendered in (first,final):
            self.assertEqual(rendered['net']['tls']['mode'],'requireTLS')
            self.assertEqual(rendered['security']['authorization'],'enabled')
            self.assertNotIn('allowInvalidCertificates',rendered['net']['tls'])
        self.assertIn(value['node']['address'],final['net']['bindIp'])

    def test_identifiers_versions_and_path_injection_rejected(self):
        for field, malicious in [('user','x; DROP DATABASE music'),('database','x\ntrust')]:
            value = self.runtime('postgresql');value['database'][field]=malicious
            with self.assertRaises(ValueError):dc.validate(value)
        value = self.runtime('mongodb');value['database_versions']['mongodb']['packages'][0]['filename']='../unsafe.deb'
        with self.assertRaises(ValueError):dc.validate(value)
        value = self.runtime('postgresql');value['database']['port']=True
        with self.assertRaises(ValueError):dc.validate(value)

    def test_postgres_local_health_uses_allowed_loopback_and_verified_tls(self):
        with patch.object(db,'run') as run:
            db.health(self.runtime('postgresql'))
            args=run.call_args_list[0].args;env=run.call_args_list[0].kwargs['env']
            self.assertEqual(args[args.index('-h')+1],'127.0.0.1')
            self.assertEqual(env['PGSSLMODE'],'verify-full')
            self.assertNotIn(self.env['POSTGRES_APP_PASSWORD'],args)

    def test_workstation_guard_precedes_mutations(self):
        with patch.object(db.platform,'system',return_value='Darwin'), patch.object(db,'run') as run:
            with self.assertRaises(ValueError):db.guard(self.runtime('postgresql'))
            run.assert_not_called()

    def test_command_errors_do_not_echo_secret_output(self):
        secret = self.env['POSTGRES_APP_PASSWORD']
        with patch.object(db.subprocess,'run',return_value=Mock(returncode=1,stdout=secret,stderr=secret)):
            with self.assertRaises(ValueError) as error:db.run('psql')
        self.assertNotIn(secret,str(error.exception))

    def test_completed_database_checks_health_without_reinstall(self):
        value = self.runtime('postgresql')
        identity = {**value['aws'],'node':value['node']['name'],'kind':'postgresql',
                    'desired_sha256':db.hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()}
        with tempfile.TemporaryDirectory() as folder, patch.object(db,'BASE',Path(folder)):
            state=Path(folder)/'aws-state'/value['aws']['generation'];state.mkdir(parents=True)
            (state/'postgresql-identity.json').write_text(json.dumps(identity))
            (state/'postgresql-installed.json').write_text('{}')
            with patch.object(db,'install_packages') as packages, patch.object(db,'health') as health:
                db.install(value);packages.assert_not_called();health.assert_called_once_with(value)
            changed=copy.deepcopy(value);changed['env']['POSTGRES_APP_PASSWORD']='different_'+'Z'*40
            with self.assertRaises(ValueError):db.install(changed)

    def test_systemd_requires_data_mount_and_has_no_credentials(self):
        for kind in dc.KINDS:
            unit=dc.unit(kind)
            self.assertIn('RequiresMountsFor=/var/lib/music-cluster/',unit)
            self.assertIn('NoNewPrivileges=true',unit)
            self.assertNotIn('PASSWORD',unit)

    def test_stage_cannot_target_wrong_service(self):
        for role, stage in [('kafka','postgresql'),('postgresql','common'),('mongodb','kafka'),('advertising','mongodb')]:
            self.assertFalse(install.stage_allowed(stage,{'role':role}))
        for role, stage in [('postgresql','postgresql'),('mongodb','database-health'),('advertising','application-host'),('control','application-host')]:
            self.assertTrue(install.stage_allowed(stage,{'role':role}))

    def test_all_packages_are_offline_node_scoped_and_exclude_ca_key(self):
        def fake_pki(config, directory):
            directory.mkdir(parents=True,exist_ok=True)
            (directory/'ca.crt').write_text('public CA fixture')
            (directory/'ca.key').write_text('private CA fixture')
            for node in config['inventory']['nodes']:
                target=directory/node['name'];target.mkdir()
                (target/'node.key').write_text('private node fixture')
                (target/'node.crt').write_text('public node fixture')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);shutil.copytree(ROOT/'installer',root/'installer',ignore=shutil.ignore_patterns('__pycache__'))
            path=root/'inventory.json';path.write_text(json.dumps(inventory(self.c)))
            with patch.object(install,'ROOT',root), patch.dict(sys.modules,{'pki':Mock(prepare=fake_pki)}), patch.object(install,'Aws') as aws:
                install.prepare(self.c,path);aws.assert_not_called()
            packages=json.loads((root/'.private/aws-dev/db-test/packages.json').read_text())
            self.assertEqual(len(packages),14)
            for package in packages:
                with tarfile.open(package['file']) as tar:
                    self.assertNotIn('ca.key',[Path(n).name for n in tar.getnames()])
                    runtime=json.load(tar.extractfile('runtime.json'))
                    if package['node']=='advertising':
                        self.assertEqual(runtime['database_client']['kind'],'mongodb')
                        self.assertNotIn('MONGO_ADMIN_PASSWORD',json.dumps(runtime))
                    elif package['node'].startswith('control-'):
                        self.assertEqual(runtime['database_client']['kind'],'postgresql')
                        self.assertNotIn('MONGO_ADMIN_PASSWORD',json.dumps(runtime))

    def test_database_certificates_include_loopback_san(self):
        import ssl
        sys.path.insert(0,str(ROOT/'installer/core/lib'))
        import pki
        nodes=[{'name':'postgresql','address':'10.80.16.20','roles':['postgresql']},
               {'name':'control-a','address':'10.80.16.10','roles':['control']}]
        with tempfile.TemporaryDirectory() as folder:
            pki.prepare({'env':{'ENVIRONMENT':'aws'},'inventory':{'nodes':nodes}},Path(folder))
            pg=ssl._ssl._test_decode_cert(str(Path(folder)/'postgresql/node.crt'))
            control=ssl._ssl._test_decode_cert(str(Path(folder)/'control-a/node.crt'))
            self.assertIn(('IP Address','127.0.0.1'),pg['subjectAltName'])
            self.assertIn(('DNS','localhost'),pg['subjectAltName'])
            self.assertNotIn(('IP Address','127.0.0.1'),control['subjectAltName'])


if __name__=='__main__':unittest.main()
