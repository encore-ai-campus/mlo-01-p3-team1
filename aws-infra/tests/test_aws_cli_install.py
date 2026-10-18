import base64
import hashlib
import importlib.util
from pathlib import Path
import stat
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cli_install',ROOT/'installer/aws-cli.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)


class SignedCliInstallation(unittest.TestCase):
    def test_corrupt_bytes_are_rejected_before_signature_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);a=p/'a';a.write_bytes(b'altered')
            with patch.object(cli.subprocess,'run') as run,self.assertRaises(ValueError):
                cli.verify_signature(a,a,a,{'archive_sha256':'a'*64})
            run.assert_not_called()

    def test_valid_signature_from_another_identity_or_revoked_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);a=p/'a';a.write_bytes(b'fixture');key=p/'key'
            key.write_text('-----BEGIN PGP PUBLIC KEY BLOCK-----\n'+base64.b64encode(b'fixture public key').decode()+'\n-----END PGP PUBLIC KEY BLOCK-----\n')
            lock={'archive_sha256':cli.sha(a),'signature_sha256':cli.sha(a),'public_key_sha256':cli.sha(key),'signer_fingerprint':'A'*40}
            for output in ('[GNUPG:] VALIDSIG '+'B'*40+' remainder','[GNUPG:] VALIDSIG '+'A'*40+' remainder\n[GNUPG:] REVKEYSIG fixture'):
                with self.subTest(output=output),patch.object(cli.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=output)),self.assertRaises(ValueError):
                    cli.verify_signature(a,a,key,lock,verifier='/usr/bin/gpgv')

    def test_archive_traversal_and_links_are_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            for index,name in enumerate(('../outside','/absolute','other/install','aws/link')):
                archive=p/(str(index)+'.zip');out=p/('out'+str(index));item=zipfile.ZipInfo(name)
                if name=='aws/link':item.external_attr=(stat.S_IFLNK|0o777)<<16
                with zipfile.ZipFile(archive,'w') as z:z.writestr(item,b'fixture')
                with self.assertRaises(ValueError):cli.extract_verified(archive,out)
                self.assertFalse(out.exists())

    def test_verified_extraction_preserves_executability_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);a=p/'archive.zip';out=p/'out';item=zipfile.ZipInfo('aws/install');item.external_attr=(stat.S_IFREG|0o755)<<16
            with zipfile.ZipFile(a,'w') as z:z.writestr(item,b'fixture')
            cli.extract_verified(a,out);self.assertEqual((out/'aws/install').stat().st_mode&0o777,0o755)
            with self.assertRaises(ValueError):cli.extract_verified(a,out)


if __name__=='__main__':unittest.main()
