"""Fault-injected storage tests, NOT real Kafka/Spark checkpoint recovery proof."""
import copy
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import patch

from pipeline.weather import es_latest
from pipeline.weather.common import OBS, KST


def observations(nx=60, minute=0):
    at = datetime(2026, 11, 3, 12, minute, tzinfo=KST)
    return [dict(_id=f'{nx}-{minute}-{category}', nx=nx, ny=127, source='odam',
                 category=category, issued_at=at.isoformat(), target_at=at.isoformat(),
                 received_at=(at + timedelta(minutes=1)).isoformat(),
                 source_hash='hash-' + str(minute), rule_version='normalize_v2',
                 measurement={'status': 'valid', 'value': 0, 'unit': 'code' if category == 'PTY' else 'unit'})
            for category in OBS]


class MemoryES:
    def __init__(self):
        self.saved = {}
        self.fail_before = None
        self.lose_response = False
        self.conflict_once = False

    def request(self, base, method, path, body=None):
        parsed = urlsplit(path)
        if parsed.path == '/weather-test':
            return {}
        identifier = parsed.path.rsplit('/', 1)[-1]
        previous = self.saved.get(identifier)
        if method == 'GET':
            if previous is None:
                raise HTTPError('http://test', 404, 'missing', None, None)
            return copy.deepcopy(previous)
        if identifier == self.fail_before:
            self.fail_before = None
            raise OSError('injected_store_unavailable')
        if self.conflict_once:
            self.conflict_once = False
            raise HTTPError('http://test', 409, 'conflict', None, None)
        query = parse_qs(parsed.query)
        if previous:
            if query.get('if_seq_no') != [str(previous['_seq_no'])] or query.get('if_primary_term') != ['1']:
                raise HTTPError('http://test', 409, 'conflict', None, None)
        elif query.get('op_type') != ['create']:
            raise AssertionError('missing create condition')
        self.saved[identifier] = {'_source': copy.deepcopy(body),
                                  '_seq_no': previous['_seq_no'] + 1 if previous else 0,
                                  '_primary_term': 1}
        if self.lose_response:
            self.lose_response = False
            raise TimeoutError('injected_response_loss_after_commit')
        return {'result': 'updated' if previous else 'created', '_shards': {'failed': 0}}


class StorageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryES()
        self.config = patch.object(es_latest, 'configuration', return_value=('http://test', 'weather-test'))
        self.transport = patch.object(es_latest, 'request', side_effect=self.store.request)
        self.config.start()
        self.transport.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(self.transport.stop)

    def test_response_lost_after_save_replay_is_noop(self):
        self.store.lose_response = True
        with self.assertRaises(TimeoutError):
            es_latest.write_grid(60, 127, observations())
        saved = copy.deepcopy(self.store.saved)
        self.assertFalse(es_latest.write_grid(60, 127, observations()))
        self.assertEqual(self.store.saved, saved)
        self.assertEqual(self.store.saved['60_127']['_source']['revision'], 1)

    def test_partial_multi_grid_write_replay_completes_without_duplication(self):
        self.store.fail_before = '61_127'
        with self.assertRaises(OSError):
            for nx in (60, 61):
                es_latest.write_grid(nx, 127, observations(nx))
        self.assertEqual(set(self.store.saved), {'60_127'})
        changes = [es_latest.write_grid(nx, 127, observations(nx)) for nx in (60, 61)]
        self.assertEqual(changes, [False, True])
        self.assertEqual(set(self.store.saved), {'60_127', '61_127'})
        for item in self.store.saved.values():
            self.assertEqual(item['_source']['revision'], 1)
            self.assertEqual(len(item['_source']['rows']), len(OBS))

    def test_recovery_after_conflict_and_old_replay_keeps_latest_round(self):
        es_latest.write_grid(60, 127, observations())
        self.store.conflict_once = True
        es_latest.write_grid(60, 127, observations(minute=10))
        current = copy.deepcopy(self.store.saved)
        self.assertFalse(es_latest.write_grid(60, 127, observations()))
        self.assertEqual(current, self.store.saved)
        self.assertEqual(self.store.saved['60_127']['_source']['revision'], 2)


if __name__ == '__main__':
    unittest.main()
