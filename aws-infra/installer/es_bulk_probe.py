#!/usr/bin/env python3
"""Bounded Driver-side REST acceptance, independent of application publishing code.

Only a fresh cluster-smoke index is created. No deletion, checkpoint operation,
automatic HTTP retry, mapping update, role change or executor secret broadcast.
"""
import argparse
import base64
import ipaddress
import json
from pathlib import Path
import re
import ssl
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


class BulkRejected(ValueError):
    """The caller must fail its batch; a 200 HTTP response is insufficient."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Probe redirects are forbidden')


def settings(value):
    if not re.fullmatch(r'[0-9a-f]{16}', value['test_id']):
        raise ValueError('Explicit fresh 16-hex test ID required')
    for key in ('project', 'environment', 'generation'):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}', value[key]):
            raise ValueError('Invalid installation namespace')
    expected = 'cluster-smoke-rest-' + value['test_id']
    if value['index'] != expected or value['username'] != 'pipeline_writer':
        raise ValueError('Only an isolated probe index and existing pipeline writer are allowed')
    if len(value['urls']) != 3 or len(set(value['urls'])) != 3:
        raise ValueError('Exactly the three provisioned ES endpoints are required')
    for url in value['urls']:
        parsed = urlsplit(url)
        address = ipaddress.ip_address(parsed.hostname)
        if (parsed.scheme != 'https' or parsed.port != 9200 or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password or address.version != 4
                or not any(address in ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))):
            raise ValueError('Use provisioned private ES HTTPS endpoints without URL credentials')
    if value['ca'] not in ('/etc/music-cluster/control/tls/ca.crt', '/etc/music-cluster/spark/tls/ca.crt'):
        raise ValueError('Use the provisioned service CA')
    if not isinstance(value['password'], str) or not value['password']:
        raise ValueError('Private writer credential required')
    return value


def bulk_body(index, documents):
    if not re.fullmatch(r'cluster-smoke-rest-[0-9a-f]{16}', index):
        raise ValueError('Business indices are outside the probe scope')
    if not 1 <= len(documents) <= 64 or len({i for i, _ in documents}) != len(documents):
        raise ValueError('Use 1..64 distinct deterministic document IDs')
    lines = []
    for identifier, document in documents:
        if not re.fullmatch(r'row-[0-9]{1,2}|invalid', identifier):
            raise ValueError('Invalid synthetic ID')
        lines.extend((json.dumps({'index': {'_index': index, '_id': identifier}}, separators=(',', ':')),
                      json.dumps(document, separators=(',', ':'), allow_nan=False)))
    data = ('\n'.join(lines) + '\n').encode()
    if len(data) > 256 * 1024:
        raise ValueError('Probe body exceeds its bound')
    return data


def check_bulk(response, index, documents):
    items = response.get('items')
    if not isinstance(items, list) or len(items) != len(documents) or type(response.get('errors')) is not bool:
        raise BulkRejected('Incomplete or invalid bulk acknowledgement')
    failures = []
    for item, (identifier, _) in zip(items, documents):
        result = item.get('index') if isinstance(item, dict) and set(item) == {'index'} else None
        if not isinstance(result, dict) or result.get('_index') != index or result.get('_id') != identifier:
            raise BulkRejected('Bulk acknowledgement target or order mismatch')
        if type(result.get('status')) is not int or result['status'] not in (200, 201) or 'error' in result:
            failures.append(result.get('status'))
    if failures or response['errors']:
        # Do not copy error reasons/documents or credentials to logs.
        raise BulkRejected('Bulk items failed; batch must not be committed')
    return len(items)


class Client:
    def __init__(self, config):
        self.config = settings(config)
        context = ssl.create_default_context(cafile=config['ca'])
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
        self.authorization = 'Basic ' + base64.b64encode((config['username'] + ':' + config['password']).encode()).decode()

    def call(self, path, method='GET', body=None, *, ndjson=False, endpoint=0):
        allowed = ('/', '/_cluster/health', '/' + self.config['index'], '/' + self.config['index'] + '/_bulk',
                   '/' + self.config['index'] + '/_search')
        if path not in allowed or method not in ('GET', 'HEAD', 'PUT', 'POST'):
            raise ValueError('Request is outside the bounded probe')
        data = body if ndjson else (json.dumps(body).encode() if body is not None else None)
        req = Request(self.config['urls'][endpoint] + path, data=data, method=method,
                      headers={'Authorization': self.authorization, 'Content-Type': 'application/x-ndjson' if ndjson else 'application/json'})
        try:
            with self.opener.open(req, timeout=15) as response:
                return None if method == 'HEAD' else json.load(response)
        except HTTPError as error:
            # Neither response bodies nor URLs are included in raised errors.
            status = error.code;error.close()
            if method == 'HEAD' and status == 404:
                return False
            raise ValueError('ES probe HTTP status ' + str(status)) from None


def exercise(client, documents):
    c = client.config;index = c['index']
    if len(documents) != 18 or {i for i, _ in documents} != {'row-' + str(i) for i in range(18)}:
        raise ValueError('Exactly 18 synthetic rows are required')
    for endpoint in range(3):
        if client.call('/', endpoint=endpoint)['version']['number'] != '8.19.23':
            raise ValueError('Provisioned ES version differs from the reviewed version')
    health = client.call('/_cluster/health')
    if health.get('number_of_nodes') != 3 or health.get('status') != 'green':
        raise ValueError('Three green ES nodes required')
    if client.call('/' + index, 'HEAD') is not False:
        raise ValueError('Probe index exists; inspect evidence instead of resetting or replaying')
    client.call('/' + index, 'PUT', {'settings': {'number_of_shards': 1, 'number_of_replicas': 1},
        'mappings': {'dynamic': 'strict', '_meta': {'infra_probe': 'rest-bulk', 'project': c['project'],
            'environment': c['environment'], 'generation': c['generation'], 'test_id': c['test_id']},
            'properties': {'id': {'type': 'long'}, 'score': {'type': 'long'}}}})
    path = '/' + index + '/_bulk'
    for _ in range(2):
        check_bulk(client.call(path, 'POST', bulk_body(index, documents), ndjson=True), index, documents)
    mixed = [documents[0], ('invalid', {'id': 99, 'score': 'not-an-integer'})]
    response = client.call(path, 'POST', bulk_body(index, mixed), ndjson=True)
    statuses = [i['index']['status'] for i in response.get('items', [])]
    if len(statuses) != 2 or statuses[0] != 200 or statuses[1] != 400 or response.get('errors') is not True:
        raise ValueError('Expected partial bulk mapping rejection was not observed')
    try:
        check_bulk(response, index, mixed)
    except BulkRejected:
        pass
    else:
        raise ValueError('Partial bulk error was treated as success')
    expected = {identifier: value for identifier, value in documents}
    for _ in range(20):
        response = client.call('/' + index + '/_search', 'POST', {'size': 64, 'track_total_hits': True, 'query': {'match_all': {}}})
        if response.get('timed_out') or response.get('_shards', {}).get('failed', 0):
            raise ValueError('Incomplete search acknowledgement')
        hits = response['hits']['hits']
        if response['hits']['total'] == {'value': 18, 'relation': 'eq'} and {h['_id']: h['_source'] for h in hits} == expected:
            return {'rows': 18, 'duplicate_or_missing_rows': 0, 'deterministic_id_replay': True,
                    'partial_bulk_error_rejected': True, 'tls_hostname_verification': True, 'es_endpoints': 3,
                    'credential_user': 'pipeline_writer', 'index_preserved': True, 'automatic_http_retry': False,
                    'scope': 'Bounded Driver-side synthetic REST/Bulk; not application exactly-once or weather publication acceptance'}
        time.sleep(1)
    raise ValueError('Search results differ from the acknowledged synthetic rows')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True);parser.add_argument('--result', required=True)
    parser.add_argument('--execute', action='store_true');args = parser.parse_args()
    if not args.execute:
        print('Preparation only; no ES request or Spark application submitted');return
    output = Path(args.result)
    if output.exists():
        raise ValueError('Evidence exists; inspect it instead of replaying')
    cfg = settings(json.loads(Path(args.config).read_text()))
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.appName('infra-es-rest-' + cfg['test_id']).getOrCreate()
    try:
        spark.sparkContext.setLogLevel('WARN')
        rows = spark.range(18).selectExpr('id', 'id * 10 AS score').collect()
        # Bounded collect is intentional: writer credentials stay on the Driver.
        report = exercise(Client(cfg), [('row-' + str(r.id), {'id': r.id, 'score': r.score}) for r in rows])
        report.update(spark_version=spark.version, application_id=spark.sparkContext.applicationId, test_id=cfg['test_id'])
        with output.open('x') as handle:
            json.dump(report, handle, indent=2);handle.write('\n')
        output.chmod(0o600)
        print(json.dumps({'passed': True, 'rows': 18, 'partial_bulk_error_rejected': True}))
    finally:
        spark.stop()


if __name__ == '__main__':
    main()
