"""Prevent shared-login OAuth refresh fan-out after an observed 429 failure."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'bin'),str(ROOT/'lib')]
import preflight,project
from awscli import AwsError

class PreflightAuthentication(unittest.TestCase):
    def setUp(self):self.c=project.load(ROOT/'config/project.example.json')
    def test_login_failure_stops_all_account_fanout(self):
        with patch.object(preflight,'Aws',side_effect=AwsError('token refresh 429')),patch.object(preflight,'inspect_account') as inspect:
            with self.assertRaises(AwsError):preflight.scan_accounts(self.c)
            inspect.assert_not_called()
    def test_login_checked_before_any_account_worker(self):
        login=Mock()
        def scan(c,a):
            self.assertTrue(login.called)
            return a['profile']
        with patch.object(preflight,'Aws',login),patch.object(preflight,'inspect_account',side_effect=scan):
            result=preflight.scan_accounts(self.c)
        self.assertEqual(result,['encore'+str(i) for i in range(1,6)])
        self.assertEqual(login.call_args.kwargs,{'raw':True})

if __name__=='__main__':unittest.main()
