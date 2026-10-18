import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('delta_addon', ROOT / 'installer/delta.py')
delta = importlib.util.module_from_spec(spec);spec.loader.exec_module(delta)


class DeltaAddonIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.spark = self.root / 'spark';(self.spark / 'jars').mkdir(parents=True)
        base = self.spark / 'jars/base.jar';base.write_bytes(b'preserved Spark distribution')
        self.base = self.root / 'connectors.lock.json'
        self.base.write_text(json.dumps({'distribution_jars': [{'filename': base.name, 'sha256': delta.digest(base)}], 'jars': []}))
        (self.spark / 'connectors.lock.json').write_bytes(self.base.read_bytes())
        self.bundle = self.root / 'bundle';self.bundle.mkdir();entries = []
        for i in range(9):
            p = self.bundle / ('addition-' + str(i) + '.jar');p.write_bytes(('reviewed bytes ' + str(i)).encode())
            entries.append({'filename': p.name, 'sha256': delta.digest(p), 'coordinate': 'io.delta:fixture-' + str(i) + ':4.3.1'})
        manifest = {'schema_version': 1, 'candidate': 'io.delta:delta-spark_4.1_2.13:4.3.1', 'spark_version': '4.1.3', 'hadoop_version': '3.4.2', 'duplicate_class_findings': 0, 'base_connector_lock_sha256': delta.digest(self.base), 'jars': entries}
        self.reviewed = self.root / 'delta.lock.json';self.reviewed.write_text(json.dumps(manifest))
        (self.bundle / 'delta.lock.json').write_bytes(self.reviewed.read_bytes());self.addons = self.root / 'addons'

    def publish(self):
        return delta.publish(self.bundle, self.spark, self.addons, self.reviewed, self.base)

    def test_atomic_addon_and_explicit_retry_preserve_global_classpath(self):
        old = (self.spark / 'jars/base.jar').read_bytes();target, created = self.publish()
        self.assertTrue(created);self.assertEqual(len(list(target.glob('*.jar'))), 9)
        self.assertEqual(list((self.spark / 'jars').iterdir()), [self.spark / 'jars/base.jar'])
        self.assertEqual((self.spark / 'jars/base.jar').read_bytes(), old)
        self.assertEqual(self.publish(), (target, False))

    def test_corrupt_final_jar_cannot_publish_partial_addon(self):
        (self.bundle / 'addition-8.jar').write_bytes(b'corrupted')
        with self.assertRaises(ValueError): self.publish()
        self.assertFalse(self.addons.exists())

    def test_baseline_drift_and_extra_global_jar_are_blocked(self):
        (self.spark / 'jars/unreviewed.jar').write_bytes(b'unknown')
        with self.assertRaises(ValueError): self.publish()
        self.assertFalse(self.addons.exists())

    def test_bundle_cannot_replace_its_reviewed_lock(self):
        p = self.bundle / 'delta.lock.json';value = json.loads(p.read_text());value['jars'][0]['sha256'] = '0' * 64;p.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.publish()
        self.assertFalse(self.addons.exists())

    def test_existing_addon_corruption_is_not_overwritten(self):
        target, _ = self.publish();p = target / 'addition-8.jar';p.write_bytes(b'changed')
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(p.read_bytes(), b'changed')

    def test_symlink_addon_parent_is_rejected(self):
        real = self.root / 'real';real.mkdir();self.addons.symlink_to(real, target_is_directory=True)
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(list(real.iterdir()), [])

    def test_private_installer_umask_still_allows_service_user_traversal(self):
        self.addons = self.root / 'new-public-addons' / 'delta'
        old = os.umask(0o077)
        try: target, created = self.publish()
        finally: os.umask(old)
        self.assertTrue(created)
        for p in (self.addons.parent, self.addons, target): self.assertEqual(p.stat().st_mode & 0o777, 0o755)
        self.assertEqual((target / 'addition-0.jar').stat().st_mode & 0o777, 0o644)


if __name__ == '__main__': unittest.main()
