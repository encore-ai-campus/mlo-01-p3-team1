"""공식 SDK 실제 stdio 교환. SDK 미설치 시 별도 skip, 실외부 API 시험은 아님."""
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'MCP SDK is not installed')
class StdioMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_tools_payloads_and_authorization(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        root = str(Path(__file__).resolve().parents[1])
        code = ('from tests.test_store_context import make_service; '
                'from backend.store_context.server import create_server; '
                'create_server(make_service()).run(transport="stdio")')
        parameters = StdioServerParameters(command=sys.executable, args=['-c', code], cwd=root)
        async with asyncio.timeout(30):
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    self.assertEqual({t.name for t in tools.tools},
                                     {'get_store_profile', 'get_neighborhood_context', 'get_weather_context'})
                    for tool in tools.tools:
                        self.assertNotIn('principal_id', tool.inputSchema.get('properties', {}))
                        self.assertNotIn('requester_id', tool.inputSchema.get('properties', {}))
                        self.assertTrue(tool.annotations.readOnlyHint)
                    for name, expected in [('get_store_profile', 'ok'),
                                           ('get_neighborhood_context', 'empty'),
                                           ('get_weather_context', 'ok')]:
                        result = await client.call_tool(name, {'store_id': 'cafe'})
                        self.assertFalse(result.isError)
                        self.assertEqual(result.structuredContent['status'], expected)
                    denied = await client.call_tool('get_store_profile', {'store_id': 'other'})
                    self.assertTrue(denied.isError)
                    bad_radius = await client.call_tool('get_neighborhood_context', {'store_id': 'cafe', 'radius_m': 5000})
                    self.assertTrue(bad_radius.isError)
                    from backend.store_context.client import request_conditions
                    captured = []

                    async def host_adapter(payload):
                        captured.append(payload)
                        return {'conditions': ['quiet'], 'source': 'test_adapter_not_real_llm'}

                    result = await request_conditions(client, host_adapter, 'cafe', '대화하기 좋은 음악')
                    self.assertEqual(result['context']['status'], 'ok')
                    self.assertFalse(result['catalog_selection_verified'])
                    weather = captured[0]['store_context']['contexts']['get_weather_context']['data']
                    self.assertTrue(all(hour['usable'] for hour in weather['forecast']))

    async def test_real_cli_configuration_without_external_providers(self):
        from backend.store_context.client import read_local_server
        config = Path(__file__).resolve().parents[1] / 'config/examples/store-context.example.json'
        # Explicitly empty provider settings prevent any live API/ES request,
        # even if the person running this test has credentials in their shell.
        settings = {name: '' for name in ('KAKAO_REST_API_KEY', 'ES_URL', 'WEATHER_INDEX',
                                          'ES_USERNAME', 'ES_PASSWORD', 'ES_CA_CERT')}
        with patch.dict(os.environ, settings):
            async with asyncio.timeout(30):
                bundle = await read_local_server(config, 'example-cafe')
        self.assertEqual(bundle['status'], 'partial')
        contexts = bundle['contexts']
        self.assertEqual(contexts['get_store_profile']['data']['store_id'], 'example-cafe')
        self.assertEqual(contexts['get_neighborhood_context']['status'], 'unavailable')
        self.assertEqual(contexts['get_neighborhood_context']['warnings'], ['provider_not_configured'])
        self.assertEqual(contexts['get_weather_context']['status'], 'unavailable')
        self.assertEqual(contexts['get_weather_context']['warnings'], ['weather_unavailable'])

    async def test_partial_and_unavailable_survive_real_protocol_and_host_boundary(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from backend.store_context.client import request_conditions
        root = str(Path(__file__).resolve().parents[1])
        code = ('from datetime import timedelta; '
                'from tests.test_store_context import make_service, NOW; '
                'from backend.store_context.kakao import KakaoPlaces; '
                'from backend.store_context.server import create_server; '
                'service=make_service(places_provider=KakaoPlaces(), clock=lambda: NOW+timedelta(hours=3)); '
                'create_server(service).run(transport="stdio")')
        parameters = StdioServerParameters(command=sys.executable, args=['-c', code], cwd=root)

        async def host_adapter(payload):
            contexts = payload['store_context']['contexts']
            self.assertEqual(contexts['get_neighborhood_context']['status'], 'unavailable')
            self.assertEqual(contexts['get_weather_context']['status'], 'partial')
            weather = contexts['get_weather_context']['data']
            self.assertTrue(weather['stale_targets'])
            self.assertFalse(weather['ready'])
            self.assertTrue(weather['forecast'])
            self.assertTrue(all(not hour['usable'] for hour in weather['forecast']))
            return {'source': 'test_adapter_not_real_llm'}

        async with asyncio.timeout(30):
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    result = await request_conditions(client, host_adapter, 'cafe', '차분한 음악')
        self.assertEqual(result['context']['status'], 'partial')
        self.assertFalse(result['catalog_selection_verified'])


if __name__ == '__main__':
    unittest.main()
