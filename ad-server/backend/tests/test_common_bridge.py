import json
from email.message import Message
from unittest.mock import MagicMock, patch
from django.http import HttpResponse
from django.test import SimpleTestCase, RequestFactory, override_settings
from api import common_bridge
from domains.ads.errors import DomainError


@override_settings(DEBUG=True,ADS_COMMON_API_URL='http://127.0.0.1:8001',ADS_INTERNAL_SECRET='test-secret')
class CommonBridgeTests(SimpleTestCase):
    def reply(self,body):
        result=MagicMock();result.__enter__.return_value=result
        result.read.return_value=json.dumps(body).encode()
        result.headers=Message();result.headers.add_header('Set-Cookie','cafe_guest=opaque; HttpOnly; Path=/; SameSite=Lax')
        return result

    def test_guest_cookie_forward_and_no_browser_assertions(self):
        request=RequestFactory().get('/',HTTP_COOKIE='cafe_guest=opaque',HTTP_X_ROLE='ADMIN')
        with patch.object(common_bridge,'build_opener') as opener:
            opener.return_value.open.return_value=self.reply({'owner_guest_id':'verified','measurement_available':True})
            context=common_bridge.resolve_guest(request,bootstrap=False)
            message=opener.return_value.open.call_args.args[0]
            self.assertEqual(message.get_header('Cookie'),'cafe_guest=opaque')
            self.assertNotIn('X-role',message.headers)
            self.assertEqual(context.owner_guest_id,'verified')
            response=context.response_finalizer(HttpResponse())
            self.assertTrue(response.cookies['cafe_guest']['httponly'])

    @override_settings(DEBUG=False)
    def test_non_tls_production_bridge_is_rejected_before_request(self):
        with patch.object(common_bridge,'build_opener') as opener:
            with self.assertRaises(DomainError):common_bridge.call_common(RequestFactory().get('/'),'admin')
            opener.assert_not_called()

    def test_network_exception_is_sanitized(self):
        with patch.object(common_bridge,'build_opener') as opener:
            opener.return_value.open.side_effect=RuntimeError('sensitive internal URL and credentials')
            with self.assertRaises(DomainError) as caught:common_bridge.call_common(RequestFactory().get('/'),'admin')
            self.assertNotIn('credentials',str(caught.exception))

    def test_oversized_identity_response_fails_closed(self):
        with patch.object(common_bridge,'build_opener') as opener:
            response=self.reply({});response.read.return_value=b' '*65537
            opener.return_value.open.return_value=response
            with self.assertRaises(DomainError):common_bridge.call_common(RequestFactory().get('/'),'admin')
