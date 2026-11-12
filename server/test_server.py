import hashlib
import hmac
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server.analysis import AnalysisError, generate_daily, parse_response, relay_post, report_view
from server.app import ThreadedServer, dashboard, make_handler
from server.statistics import DAY, MINUTE, analysis_input, historical_profile, metrics
from server.storage import Store, now_ms, validate_batch


def reading(at, value=6.2, trend='→', historical=False):
    return {'sourceAt': at, 'value': value, 'trend': trend, 'historical': historical}


def response_payload():
    result = {'summary': '合成测试报告，覆盖不足时不判断长期趋势。',
              'sections': [{'title': '最近24小时', 'text': '合成资料仅用于接口测试。'}], 'limitations': ['非诊断。']}
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(result)}]}]}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'data.sqlite3')
        self.now = 1794200000000

    def tearDown(self):
        self.temp.cleanup()

    def test_idempotence_and_audited_correction(self):
        first = reading(self.now)
        self.assertEqual(self.store.ingest([first], self.now)['inserted'], 1)
        self.assertEqual(self.store.ingest([first], self.now)['unchanged'], 1)
        changed = reading(self.now, 6.5, '↗')
        self.assertEqual(self.store.ingest([changed], self.now+1000)['corrected'], 1)
        self.assertEqual(self.store.ingest([reading(self.now, 6.2, '?', True)], self.now+2000)['unchanged'], 1)
        self.assertEqual(self.store.latest()['trend'], '↗')
        self.assertEqual(self.store.latest()['value'], 6.5)
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM revisions').fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['old_value'], 6.2)
            self.assertEqual(rows[0]['new_value'], 6.5)

    def test_invalid_packet_is_rejected_before_transaction(self):
        for value in [True, 0, -1, 60.1, 10**400, float('nan'), float('inf'), '6.2']:
            with self.assertRaises(ValueError):
                validate_batch({'readings': [reading(self.now, value)]}, self.now)
        for timestamp in [True, 0, self.now+90001, '1794200000000', float(self.now)]:
            with self.assertRaises(ValueError):
                validate_batch({'readings': [reading(timestamp)]}, self.now)
        with self.assertRaises(ValueError):
            validate_batch({'readings': [reading(self.now), reading(self.now, 0)]}, self.now)
        self.assertIsNone(self.store.latest())
        valid = validate_batch({'readings': [reading(self.now, .1), reading(self.now, 60, '↟')]}, self.now)
        self.assertEqual(len(valid), 2)

    def test_empty_dashboard_has_no_fabricated_zero(self):
        data = dashboard(self.store, self.now)
        self.assertIsNone(data['latest'])
        self.assertIsNone(data['metrics']['mean'])
        self.assertIsNone(data['metrics']['inRangePercent'])
        self.assertEqual(data['metrics']['coveragePercent'], 0)
        self.assertEqual(data['analysis']['status'], 'waiting')

    def test_repeated_phone_arrows_are_valid_but_strings_are_bounded(self):
        for trend in ['?', '↑↑↑', '↓'*32, '↟', '↡', '↗↗']:
            items = validate_batch({'readings': [reading(self.now, trend=trend)]}, self.now)
            self.assertEqual(items[0]['trend'], trend)
        for trend in ['', 'up', '→ ', '→\n', '↑'*33, '→<script>']:
            with self.assertRaises(ValueError):
                validate_batch({'readings': [reading(self.now, trend=trend)]}, self.now)


class StatisticsTests(unittest.TestCase):
    def test_time_weights_gap_and_not_interpolated(self):
        points = [reading(0, 3.8), reading(5*MINUTE, 6), reading(25*MINUTE, 12)]
        result = metrics(points, 0, 30*MINUTE)
        self.assertEqual(result['coveragePercent'], 50)
        self.assertEqual(result['observedMinutes'], 15)
        self.assertEqual(result['inRangePercent'], 33.33)
        self.assertEqual(result['belowRangePercent'], 33.33)
        self.assertEqual(result['aboveRangePercent'], 33.33)
        self.assertAlmostEqual(result['mean'], (3.8+6+12)/3, places=2)
        self.assertTrue(result['limitations'])

    def test_dense_packets_do_not_gain_extra_time_weight(self):
        result = metrics([reading(0, 4), reading(MINUTE, 10)], 0, 6*MINUTE)
        self.assertEqual(result['coveragePercent'], 100)
        self.assertEqual(result['mean'], 9)
        self.assertEqual(result['inRangePercent'], 16.67)
        self.assertEqual(result['diabetesReferenceInRangePercent'], 100)

    def test_period_edges_and_coverage_null(self):
        result = metrics([reading(0, 6)], 2*MINUTE, 6*MINUTE)
        self.assertEqual(result['observedMinutes'], 3)
        self.assertEqual(result['sampleCount'], 0)
        empty = metrics([reading(0)], 10*MINUTE, 20*MINUTE)
        self.assertIsNone(empty['mean'])

    def test_historical_profile_weights_days_not_packet_counts(self):
        start = 1794000000000//DAY*DAY
        points = [reading(start+i*1000, 5) for i in range(20)] + [reading(start+DAY, 9)]
        result = historical_profile(points, start, start+2*DAY)
        self.assertEqual(result['daysAvailable'], 2)
        self.assertEqual(result['points'][0]['median'], 7)
        self.assertEqual(result['points'][0]['p25'], 6)
        self.assertEqual(result['points'][0]['p75'], 8)


class AnalysisTests(unittest.TestCase):
    setUp = StorageTests.setUp
    tearDown = StorageTests.tearDown

    def fill_history(self, days=4):
        samples = [reading(self.now-i*5*MINUTE) for i in reversed(range(days*288+1))]
        self.store.ingest(samples, self.now)

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_gate_idempotence_and_completed_report(self):
        calls = []
        invoke = lambda payload, date: calls.append(payload) or response_payload()
        self.assertEqual(generate_daily(self.store, self.now, invoke)['status'], 'insufficient_history')
        self.fill_history(3)
        self.assertEqual(generate_daily(self.store, self.now, invoke)['status'], 'insufficient_history')
        self.fill_history(4)
        self.assertEqual(generate_daily(self.store, self.now, invoke)['status'], 'ready')
        self.assertEqual(generate_daily(self.store, self.now, invoke)['status'], 'already_attempted')
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]['store'])
        self.assertEqual(calls[0]['text']['format']['type'], 'json_schema')
        report = report_view(self.store)
        self.assertEqual(report['status'], 'ready')
        self.assertFalse(any('14天' in item for item in report['limitations']))
        self.assertEqual(report['sources'], [])

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_timeout_does_not_retry_and_preserves_previous_report(self):
        self.fill_history()
        self.assertEqual(generate_daily(self.store, self.now, lambda *_: response_payload())['status'], 'ready')
        self.store.ingest([reading(self.now+DAY-5*MINUTE)], self.now+DAY)
        def failure(*_):
            raise AnalysisError('relay_network_error')
        self.assertEqual(generate_daily(self.store, self.now+DAY, failure)['status'], 'error')
        self.assertEqual(generate_daily(self.store, self.now+DAY, failure)['status'], 'already_attempted')
        old = report_view(self.store)
        self.assertEqual(old['status'], 'error')
        self.assertTrue(old['summary'])
        self.assertIsNotNone(self.store.latest())

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'false'})
    def test_disabled_never_calls_model(self):
        self.fill_history()
        self.assertEqual(generate_daily(self.store, self.now, lambda *_: self.fail('model called'))['status'], 'disabled')

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_no_recent_data_skips_paid_call_without_claiming_day(self):
        self.fill_history()
        later = self.now+DAY
        result = generate_daily(self.store, later, lambda *_: self.fail('model called without recent data'))
        self.assertEqual(result['status'], 'no_recent_data')
        self.assertIsNone(self.store.report())
        self.assertIsNone(dashboard(self.store, later+10*MINUTE)['metrics']['mean'])
        self.store.ingest([reading(later-5*MINUTE)], later)
        self.assertEqual(generate_daily(self.store, later, lambda *_: response_payload())['status'], 'ready')

    def test_far_history_is_disjoint_compressed_and_missingness_preserved(self):
        self.fill_history()
        self.store.ingest([reading(self.now-100*DAY, 7), reading(self.now-200*DAY, 8), reading(self.now-364*DAY, 9)], self.now)
        payload = analysis_input(self.store.readings(), self.now)
        older = payload['older28DaySummaries']
        self.assertLessEqual(len(older), 12)
        self.assertTrue(any(block['periodStartDaysBeforeCurrent'] >= 200 for block in older))
        self.assertTrue(all(block['periodEndDaysBeforeCurrent'] >= 56 for block in older))
        self.assertTrue(all(block['coveragePercent'] < 1 for block in older))
        self.assertTrue(all(block['sampleCount'] == 1 for block in older))
        self.assertEqual(payload['comparisonAvailability'][-1]['bothHaveObservations'], False)

    def test_payload_keeps_raw_recent_and_historical_coverage(self):
        self.fill_history()
        payload = analysis_input(self.store.readings(), self.now)
        self.assertLessEqual(len(payload['recentReadings']), 289)
        self.assertTrue(all(len(point) == 2 for point in payload['recentReadings']))
        self.assertIsNone(payload['windows']['previous14d']['mean'])
        self.assertEqual(payload['dailySummaries'][-1]['coveragePercent'], 100)

    def test_invalid_model_output_is_not_published(self):
        for response in [{'status': 'incomplete'}, {'status': 'completed', 'output': []},
                         {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{}'}]}]}]:
            with self.assertRaises(AnalysisError):
                parse_response(response)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'data.sqlite3')
        self.server = ThreadedServer(('127.0.0.1', 0), make_handler(self.store, 'i'*32, 'r'*32, 'a'*32))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def fetch(self, path, token=None, data=None, method=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = Request(self.base+path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def test_auth_read_token_is_read_only_and_retries_atomic(self):
        payload = {'readings': [reading(now_ms()-300000)]}
        self.assertEqual(self.fetch('/health')[0], 200)
        self.assertEqual(self.fetch('/api/v1/dashboard')[0], 401)
        self.assertEqual(self.fetch('/api/v1/readings', 'r'*32, payload)[0], 401)
        code, body = self.fetch('/api/v1/readings', 'i'*32, payload)
        self.assertEqual((code, body['accepted'], body['inserted']), (200, 1, 1))
        code, body = self.fetch('/api/v1/readings', 'i'*32, payload)
        self.assertEqual((code, body['unchanged']), (200, 1))
        self.assertEqual(self.fetch('/api/v1/dashboard', 'r'*32)[1]['latest']['value'], 6.2)
        bad = {'readings': [reading(now_ms()), reading(now_ms(), 0)]}
        self.assertEqual(self.fetch('/api/v1/readings', 'i'*32, bad)[0], 400)
        self.assertEqual(len(self.store.readings()), 1)

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_manual_analysis_capability_is_not_read_or_ingest_access(self):
        self.assertEqual(self.fetch('/api/v1/analysis','r'*32,method='POST')[0],401)
        self.assertEqual(self.fetch('/api/v1/analysis','a'*32,method='POST')[0],409)
        self.assertEqual(self.fetch('/api/v1/dashboard','a'*32)[0],401)
        self.assertEqual(self.fetch('/api/v1/readings','a'*32,{'readings':[reading(now_ms())]})[0],401)
        self.assertEqual(self.fetch('/api/v1/analysis','a'*32,{})[0],400)
        self.assertIsNone(self.store.manual_report())

    def test_manual_analysis_empty_post_submits_once(self):
        with patch('server.app.request_manual', return_value=(202, {'status': 'running'})) as submit:
            code, body = self.fetch('/api/v1/analysis', 'i'*32, method='POST')
            self.assertEqual((code, body['status']), (202, 'running'))
            code, body = self.fetch('/api/v1/analysis', 'i'*32, {})
            self.assertEqual((code, body['error']), (400, 'invalid_user_context'))
            submit.assert_called_once_with(self.store)


class RelaySignatureTests(unittest.TestCase):
    @patch.dict(os.environ, {'OPENAI_RELAY_URL': 'http://127.0.0.1:18779',
                             'OPENAI_RELAY_SERVICE_ID': 'ottai-test', 'OPENAI_RELAY_CLIENT_SECRET': 's'*32})
    def test_exact_body_and_identity_are_signed(self):
        seen = []
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"status":"completed","output":[]}'
        class FakeOpener:
            def open(self, request, timeout):
                seen.append(request)
                return FakeResponse()
        with patch('server.analysis.build_opener', return_value=FakeOpener()):
            relay_post({'store': False, 'input': '合成'}, '2026-11-09')
        req = seen[0]
        headers = {k.lower(): v for k, v in req.header_items()}
        fields = ['POST', '/v1/responses', 'ottai-test', 'application/json',
                  headers['x-relay-timestamp'], headers['x-relay-nonce'], headers['x-relay-request-id'],
                  hashlib.sha256(req.data).hexdigest()]
        signature = hmac.new(b's'*32, '\n'.join(fields).encode(), hashlib.sha256).hexdigest()
        self.assertEqual(signature, headers['x-relay-signature'])
        self.assertEqual(len(headers['x-relay-request-id']), 64)
        self.assertIn('合成', req.data.decode())



# Rolling manual reports have independent snapshot identities and a persistent cooldown.
class ManualAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'manual.sqlite3')
        self.now = 1794280000000

    def tearDown(self):
        self.temp.cleanup()

    def full_day(self):
        self.store.ingest([reading(self.now-DAY+i*5*MINUTE) for i in range(289)], self.now)

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_24h_manual_allowed_while_scheduled_waits_for_72h(self):
        from server.analysis import manual_status, request_manual
        self.full_day()
        self.assertTrue(manual_status(self.store, self.now)['eligible'])
        self.assertEqual(generate_daily(self.store, self.now, lambda *_: self.fail('paid call'))['status'], 'insufficient_history')
        jobs = []
        self.assertEqual(request_manual(self.store, self.now, launch=jobs.append)[0], 202)
        with patch('server.analysis.relay_post', return_value=response_payload()): jobs[0]()
        self.assertEqual(json.loads(self.store.manual_report()['body'])['trigger'], 'manual24h')
        self.assertIsNone(self.store.report(), 'manual cannot overwrite or consume daily claim')
        self.assertFalse(manual_status(self.store, self.now)['eligible'])

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_quality_keeps_span_freshness_and_reports_long_gaps(self):
        from server.excursions import day_quality
        short = [reading(self.now-23*60*MINUTE+i*5*MINUTE) for i in range(277)]
        self.assertFalse(day_quality(short, self.now)['ready'])
        full = [reading(self.now-DAY+i*5*MINUTE) for i in range(289)]
        self.assertTrue(day_quality(full, self.now)['ready'])
        missing = [r for i,r in enumerate(full) if i not in range(80,85)]
        self.assertGreater(day_quality(missing, self.now)['coveragePercent'], 95)
        self.assertTrue(day_quality(missing, self.now)['ready'])
        self.assertEqual(day_quality(missing, self.now)['maxGapMinutes'], 25)
        self.assertTrue(day_quality(missing, self.now)['hasLongGap'])
        self.assertIn('25分钟', day_quality(missing, self.now)['gapNotice'])
        self.assertFalse(day_quality(full[:-4], self.now)['ready'])

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_manual_accepts_75_percent_without_filling_long_gaps(self):
        from server.excursions import day_quality
        from server.analysis import manual_status, request_manual
        full = [reading(self.now-DAY+i*5*MINUTE) for i in range(289)]
        exactly75 = [r for i,r in enumerate(full) if i not in range(80,152)]
        quality = day_quality(exactly75, self.now)
        self.assertEqual(quality['coveragePercent'], 75)
        self.assertEqual(quality['maxGapMinutes'], 360)
        self.assertEqual(quality['coverageRequiredPercent'], 75)
        self.assertTrue(quality['ready'])
        self.assertIn('360分钟', quality['reason'])
        self.assertEqual(metrics(exactly75, self.now-DAY, self.now)['observedMinutes'], 1080)
        below75 = [r for i,r in enumerate(full) if i not in range(80,153)]
        self.assertFalse(day_quality(below75, self.now)['ready'])
        self.assertIn('至少75%', day_quality(below75, self.now)['reason'])
        self.store.ingest(exactly75, self.now)
        self.assertTrue(manual_status(self.store, self.now)['eligible'])
        jobs = []
        self.assertEqual(request_manual(self.store, self.now, launch=jobs.append)[0], 202)
        self.assertEqual(len(jobs), 1)

    def test_long_gap_above_75_is_context_not_a_readiness_veto(self):
        from server.excursions import day_quality
        full = [reading(self.now-DAY+i*5*MINUTE) for i in range(289)]
        gaps = set(range(80,106)) | {140,200}
        result = day_quality([r for i,r in enumerate(full) if i not in gaps], self.now)
        self.assertAlmostEqual(result['coveragePercent'], 90.28)
        self.assertEqual(result['maxGapMinutes'], 130)
        self.assertTrue(result['ready'])
        self.assertTrue(result['hasLongGap'])

    def test_lower_manual_gate_does_not_relax_complete_day_comparisons(self):
        rows = [reading(self.now-9*DAY+i*5*MINUTE) for i in range(9*288+1)]
        partial_current = (self.now-DAY+80*5*MINUTE, self.now-DAY+152*5*MINUTE)
        partial_prior = (self.now-2*DAY+80*5*MINUTE, self.now-2*DAY+108*5*MINUTE)
        rows = [r for r in rows if not any(a <= r['sourceAt'] < b for a,b in (partial_current,partial_prior))]
        reference = analysis_input(rows, self.now)['personalBaselines'][0]
        self.assertEqual(reference['eligibleDays'], 6)
        self.assertFalse(reference['comparable'], '75% permits a report, not a complete-day comparison')

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_concurrent_requests_launch_once_and_failures_are_not_retried(self):
        from server.analysis import request_manual
        from concurrent.futures import ThreadPoolExecutor
        self.full_day()
        jobs = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: request_manual(self.store, self.now, launch=jobs.append), range(8)))
        self.assertEqual(len(jobs), 1)
        with patch('server.analysis.relay_post', side_effect=AnalysisError('test_uncertain')):
            jobs[0]()
        self.assertEqual(self.store.manual_report()['status'], 'error')
        self.assertEqual(request_manual(self.store, self.now, launch=lambda _: self.fail('retried'))[0], 409)

    def test_candidate_excursions_are_descriptive_and_do_not_bridge_gaps(self):
        from server.excursions import candidate_excursions
        start = self.now-2*60*MINUTE
        values = [6.0]*8 + [6.3,6.8,7.3,7.9,8.4,8.6,8.4,7.8,7.1,6.5,6.2,6.1,6.0,6.0]
        points = [reading(start+i*5*MINUTE, v) for i,v in enumerate(values)]
        events = candidate_excursions(points,start,self.now)['events']
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event['baseline'], 6)
        self.assertEqual(event['riseAmplitude'], 2.4)
        self.assertTrue(event['returnedNearBaseline'])
        self.assertEqual(event['riseMinutes'], 25)
        self.assertIn('未确认', event['mealStatus'])
        isolated = [reading(start+i*5*MINUTE, 10 if i==8 else 6) for i in range(22)]
        self.assertEqual(candidate_excursions(isolated,start,self.now)['events'], [])
        truncated = candidate_excursions(points[:15],start,self.now)['events'][0]
        self.assertIsNone(truncated['peakToReturnMinutes'])
        broken = points[:8] + [dict(r, sourceAt=r['sourceAt']+30*MINUTE) for r in points[8:]]
        self.assertEqual(candidate_excursions(broken,start,self.now+DAY)['events'], [])

    @patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'})
    def test_multiple_dynamic_snapshots_and_fixed_calendar_report_coexist(self):
        from server.analysis import request_manual
        self.store.ingest([reading(self.now-4*DAY+i*5*MINUTE) for i in range(1153)], self.now)
        jobs = []
        self.assertEqual(request_manual(self.store, self.now, launch=jobs.append)[0], 202)
        with patch('server.analysis.relay_post', return_value=response_payload()): jobs.pop()()
        self.assertEqual(generate_daily(self.store,self.now,lambda *_:response_payload())['status'], 'ready')
        daily = self.store.latest_ready_report()
        local_end = datetime.fromtimestamp(self.now/1000, timezone(timedelta(hours=8))).replace(hour=0,minute=0,second=0,microsecond=0)
        self.assertEqual(daily['periodEnd'], int(local_end.timestamp()*1000))
        self.assertEqual(daily['reportDate'], (local_end-timedelta(days=1)).date().isoformat())
        for block in [30,60,90,120]:
            for minutes in range(block-25,block+1,5):
                self.store.ingest([reading(self.now+minutes*MINUTE)],self.now+block*MINUTE)
            self.assertEqual(request_manual(self.store,self.now+(block-25)*MINUTE,launch=jobs.append)[0],409)
            self.assertEqual(request_manual(self.store,self.now+block*MINUTE,launch=jobs.append)[0],202)
            with patch('server.analysis.relay_post',return_value=response_payload()): jobs.pop()()
        self.assertEqual(self.store.latest_ready_report(),daily)
        self.assertEqual(self.store.manual_report()['window_end'], self.now+120*MINUTE)
        with self.store.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM manual_reports').fetchone()[0],5)


    def test_manual_and_scheduled_model_calls_are_serialized(self):
        from concurrent.futures import ThreadPoolExecutor
        import time
        active=[0];peak=[0]
        def call(_):
            with self.store.analysis_lock():
                active[0]+=1;peak[0]=max(peak[0],active[0]);time.sleep(.02);active[0]-=1
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(call,range(2)))
        self.assertEqual(peak[0],1)


if __name__ == '__main__':
    unittest.main()
