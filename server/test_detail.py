"""Isolated detailed-report state, HTTP and structured-output contracts."""
import copy
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import detail
from server.analysis import AnalysisError, manual_status
from server.app import ThreadedServer, dashboard, make_handler
from server.statistics import DAY, MINUTE
from server.storage import Store

NOW = 1794326400000
CATALOG = [{'id': 'test-source', 'title': 'Synthetic scientific source',
            'url': 'https://example.invalid/synthetic-science', 'notes': 'Synthetic test notes.'}]
REAL_BUILD_CONTEXT = detail.build_context


def brief(kind='rolling', end=NOW, generated=None):
    return {'status': 'ready', 'generatedAt': generated or NOW-40*MINUTE,
            'reportDate': '2026-11-10', 'periodStart': end-DAY, 'periodEnd': end,
            'trigger': 'manual24h' if kind == 'rolling' else 'scheduled_daily',
            'summary': '合成简洁报告', 'sections': [], 'limitations': [], 'sources': []}


def report():
    return {'title': '合成详细解读', 'summary': '结合本例资料，区分观察和假设。',
            'sections': [{'title': '观察%d' % i, 'text': '合成观察资料及解释。', 'sourceIds': ['test-source']} for i in range(3)],
            'hypotheses': [{'title': '合成待验证假设', 'support': '支持的个人资料', 'against': '另一种解释及缺失的资料',
                            'verification': '如何用后续记录辨别', 'confidence': 'weak', 'sourceIds': ['test-source']}],
            'actions': [{'title': '记录调整', 'text': '围绕已观察到的现象作单项改变并比较。'}], 'limitations': []}


def output(body=None):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(body or report())}]}]}


class DetailFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.store = Store(self.path)
        self.context = {'window': {'startAt': NOW-DAY, 'endAt': NOW}, 'synthetic': 'original'}
        self.patchers = [patch.dict(os.environ, {'ANALYSIS_ENABLED': 'true'}),
                         patch('server.detail.now_ms', return_value=NOW),
                         patch('server.app.now_ms', return_value=NOW),
                         patch('server.detail.prompt_text', return_value='Synthetic detailed interpretation prompt'),
                         patch('server.detail.source_catalog', return_value=CATALOG),
                         patch('server.detail.build_context', side_effect=lambda s, p, n: copy.deepcopy(self.context))]
        for patcher in self.patchers:
            patcher.start()
        self.parent = brief()
        self.store.claim_manual('brief-one', NOW, NOW-40*MINUTE)
        self.store.finish_manual('brief-one', NOW-39*MINUTE, self.parent)
        self.report_id = detail.identity('rolling', self.parent)
        self.target = {'kind': 'rolling', 'reportId': self.report_id}

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    def run_request(self, target=None, invoke=None):
        jobs = []
        code, state = detail.request_detail(self.store, target or self.target, NOW, jobs.append, invoke or (lambda p, k: output()))
        for job in jobs:
            job()
        return code, state


class DetailTests(DetailFixture):
    def test_open_only_does_not_generate_and_ids_are_stable_and_distinct(self):
        with patch('server.detail.relay_post') as provider:
            state = detail.detail_view(self.store, 'rolling', self.report_id, NOW)
            self.assertEqual((state['status'], state['eligible'], state['report']), ('available', True, None))
            provider.assert_not_called()
        data = dashboard(self.store, NOW)
        self.assertEqual(data['rollingAnalysis']['reportId'], self.report_id)
        self.assertNotIn('reportId', data['dailyAnalysis'])
        self.assertEqual(detail.identity('rolling', dict(self.parent)), self.report_id)
        self.assertNotEqual(detail.identity('daily', self.parent), self.report_id)

    def test_frozen_job_repeated_click_and_cache_do_not_charge_twice(self):
        jobs, calls = [], []
        invoke = lambda p, k: calls.append((p, k)) or output()
        first = detail.request_detail(self.store, self.target, NOW, jobs.append, invoke)
        self.assertEqual((first[0], first[1]['status']), (202, 'running'))
        self.assertEqual(detail.request_detail(self.store, self.target, NOW+1, jobs.append, invoke)[0], 200)
        self.assertEqual(len(jobs), 1)
        with patch('server.detail.build_context', side_effect=AssertionError('running poll rebuilt context')):
            self.assertEqual(detail.detail_view(self.store, 'rolling', self.report_id, NOW+2)['status'], 'running')
        self.context['synthetic'] = 'corrected later'
        jobs[0]()
        sent = json.loads(calls[0][0]['input'][1]['content'][0]['text'])
        self.assertEqual(sent['observations']['synthetic'], 'original')
        self.assertEqual(sent['briefReport']['periodEnd'], NOW)
        self.assertEqual(calls[0][0]['max_output_tokens'], 10000)
        self.assertEqual(calls[0][0]['reasoning']['effort'], 'medium')
        self.context['synthetic'] = 'original'
        state = detail.detail_view(self.store, 'rolling', self.report_id, NOW+3)
        self.assertEqual((state['status'], state['eligible'], state['dataStale']), ('ready', False, False))
        self.assertEqual(state['report']['sources'], [{k: CATALOG[0][k] for k in ('id', 'title', 'url')}])
        self.assertEqual(detail.request_detail(self.store, self.target, NOW+4, jobs.append, invoke)[0], 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(jobs), 1)

    def test_corrected_input_needs_explicit_new_request(self):
        self.run_request()
        self.context['synthetic'] = 'correction'
        with patch('server.detail.relay_post') as provider:
            state = detail.detail_view(self.store, 'rolling', self.report_id, NOW+1)
            self.assertTrue(state['dataStale'])
            self.assertTrue(state['eligible'])
            provider.assert_not_called()
        code, state = self.run_request()
        self.assertEqual((code, state['status']), (202, 'running'))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM detail_reports').fetchone()[0], 2)

    def test_failed_corrected_attempt_retains_old_report_but_marks_it_stale(self):
        self.run_request()
        self.context['synthetic']='corrected'
        self.run_request(invoke=lambda p,k:{'status':'incomplete'})
        state=detail.detail_view(self.store,'rolling',self.report_id,NOW)
        self.assertEqual(state['status'],'error')
        self.assertIsNotNone(state['report'])
        self.assertTrue(state['dataStale'])
        self.assertFalse(state['eligible'])

    def test_old_parent_is_readable_but_cannot_generate_after_brief_changes(self):
        self.run_request()
        parent = brief(end=NOW+5*MINUTE, generated=NOW+5*MINUTE)
        self.store.claim_manual('brief-two', NOW+5*MINUTE, NOW+5*MINUTE)
        self.store.finish_manual('brief-two', NOW+5*MINUTE, parent)
        state = detail.detail_view(self.store, 'rolling', self.report_id, NOW+6*MINUTE)
        self.assertEqual(state['status'], 'ready')
        self.assertTrue(state['dataStale'])
        self.assertFalse(state['eligible'])
        self.assertEqual(detail.request_detail(self.store, self.target, NOW+6*MINUTE)[0], 409)

    def test_parent_change_while_snapshot_is_built_is_rejected_atomically(self):
        def context(s,p,n):
            updated=brief(end=NOW+5*MINUTE,generated=NOW+5*MINUTE)
            self.store.claim_manual('brief-two',NOW+5*MINUTE,NOW+5*MINUTE)
            self.store.finish_manual('brief-two',NOW+5*MINUTE,updated)
            return self.context
        with patch('server.detail.build_context',side_effect=context):
            code,state=detail.request_detail(self.store,self.target,NOW,lambda job:self.fail('launched stale parent'))
        self.assertEqual((code,state['status']),(409,'unavailable'))
        self.assertIsNone(self.store.detail_report('rolling',self.report_id,NOW))

    def test_daily_and_rolling_are_separate_and_preserve_brief(self):
        daily = brief('daily', NOW-8*3600000)
        self.store.claim_report('2026-11-10', NOW-2*MINUTE)
        self.store.finish_report('2026-11-10', NOW-MINUTE, daily)
        target = {'kind': 'daily', 'reportId': detail.identity('daily', daily)}
        self.context['window'] = {'startAt': daily['periodStart'], 'endAt': daily['periodEnd']}
        code, _ = self.run_request(target)
        state = detail.detail_view(self.store, 'daily', target['reportId'], NOW)
        self.assertEqual(code, 202)
        self.assertEqual(state['periodEnd'], daily['periodEnd'])
        self.assertEqual(self.store.latest_ready_report(), daily)
        self.assertEqual(json.loads(self.store.manual_report(ready_only=True)['body']), self.parent)
        self.assertEqual(dashboard(self.store, NOW)['dailyAnalysis']['reportId'], target['reportId'])

    def test_busy_checks_both_directions_without_brief_cooldown(self):
        self.store.ingest([{'sourceAt': NOW-i*5*MINUTE, 'value': 6.2, 'trend': '→'} for i in reversed(range(289))], NOW)
        jobs = []
        self.assertEqual(detail.request_detail(self.store, self.target, NOW, jobs.append)[0], 202)
        self.assertEqual(manual_status(self.store, NOW)['status'], 'busy')
        self.assertFalse(manual_status(self.store, NOW)['eligible'])
        self.assertEqual(self.store.claim_manual('new-brief', NOW, NOW), 'busy')
        self.context['synthetic'] = 'correction'
        self.assertEqual(detail.request_detail(self.store, self.target, NOW+1, jobs.append)[0], 409)
        self.assertEqual(len(jobs), 1)
        self.store.finish_detail(self.store.detail_report('rolling', self.report_id, NOW)['job_id'], NOW, body=detail.parse_response(output()))
        self.assertEqual(self.store.claim_manual('new-brief', NOW, NOW), 'created')
        self.assertEqual(detail.request_detail(self.store, self.target, NOW+1, jobs.append)[0], 409)
        self.assertEqual(len(jobs), 1)

    def test_recent_brief_does_not_block_detailed_interpretation(self):
        parent = brief(generated=NOW)
        self.store.finish_manual('brief-one', NOW, parent)
        with self.store.connect() as db:
            db.execute("UPDATE manual_reports SET started_at=? WHERE snapshot_id='brief-one'", (NOW-MINUTE,))
        target = {'kind': 'rolling', 'reportId': detail.identity('rolling', parent)}
        self.assertEqual(self.run_request(target)[0], 202)

    def test_uncertain_jobs_are_not_retried_and_late_completion_cannot_revive(self):
        jobs = []
        detail.request_detail(self.store, self.target, NOW, jobs.append)
        row = self.store.detail_report('rolling', self.report_id, NOW)
        expired = detail.detail_view(self.store, 'rolling', self.report_id, NOW+181000)
        self.assertEqual((expired['status'], expired['eligible']), ('error', False))
        self.store.finish_detail(row['job_id'], NOW+182000, body=detail.parse_response(output()))
        self.assertEqual(detail.detail_view(self.store, 'rolling', self.report_id, NOW+183000)['status'], 'error')
        reloaded = Store(self.path)
        self.assertEqual(detail.request_detail(reloaded, self.target, NOW+184000, jobs.append)[0], 409)
        self.assertEqual(len(jobs), 1)

    def test_cache_ttl_requires_explicit_regeneration_and_keeps_previous_report(self):
        self.run_request()
        ready=detail.detail_view(self.store,'rolling',self.report_id,NOW)
        self.assertEqual(ready['expiresAt'],NOW+8*3600000)
        self.assertFalse(detail.detail_view(self.store,'rolling',self.report_id,NOW+8*3600000-1)['eligible'])
        with patch('server.detail.relay_post') as provider:
            expired=detail.detail_view(self.store,'rolling',self.report_id,NOW+8*3600000)
            self.assertTrue(expired['eligible'])
            self.assertFalse(expired['dataStale'])
            self.assertEqual(expired['report'],ready['report'])
            provider.assert_not_called()
        jobs=[]
        code,state=detail.request_detail(self.store,self.target,NOW+8*3600000,jobs.append)
        self.assertEqual((code,state['status']),(202,'running'))
        self.assertEqual(state['report'],ready['report'])
        row=self.store.detail_report('rolling',self.report_id,NOW+8*3600000)
        self.store.finish_detail(row['job_id'],NOW+8*3600000+1,error_code='detail_uncertain')
        failed=detail.detail_view(self.store,'rolling',self.report_id,NOW+8*3600000+2)
        self.assertEqual(failed['status'],'error')
        self.assertEqual(failed['report'],ready['report'])
        self.assertFalse(failed['eligible'])
        self.assertTrue(detail.detail_view(self.store,'rolling',self.report_id,NOW+16*3600000)['eligible'])

    def test_daily_cache_ttl_is_twenty_four_hours(self):
        daily=brief('daily',NOW-8*3600000)
        self.store.claim_report('2026-11-10',NOW-MINUTE)
        self.store.finish_report('2026-11-10',NOW,daily)
        target={'kind':'daily','reportId':detail.identity('daily',daily)}
        self.run_request(target)
        state=detail.detail_view(self.store,'daily',target['reportId'],NOW)
        self.assertEqual(state['expiresAt'],NOW+24*3600000)
        self.assertFalse(detail.detail_view(self.store,'daily',target['reportId'],NOW+24*3600000-1)['eligible'])
        self.assertTrue(detail.detail_view(self.store,'daily',target['reportId'],NOW+24*3600000)['eligible'])

    def test_incomplete_and_provider_errors_do_not_replace_brief(self):
        self.run_request(invoke=lambda p, k: {'status': 'incomplete'})
        state = detail.detail_view(self.store, 'rolling', self.report_id, NOW)
        self.assertEqual(state['status'], 'error')
        self.assertIsNone(state['report'])
        self.assertEqual(json.loads(self.store.manual_report(ready_only=True)['body']), self.parent)
        self.assertEqual(detail.request_detail(self.store, self.target, NOW)[0], 409)

    def test_input_limits_and_model_schema_are_checked_before_claim(self):
        self.context['synthetic'] = '😀'*100000
        with self.assertRaisesRegex(AnalysisError, 'detail_input_limit'):
            detail.request_detail(self.store, self.target, NOW)
        self.assertIsNone(self.store.detail_report('rolling', self.report_id, NOW))
        for mutate in [lambda b: b.update(title='x'*81),
                       lambda b: b.update(sections=b['sections'][:2]),
                       lambda b: b['sections'][0].update(sourceIds=['not-whitelisted']),
                       lambda b: b['hypotheses'][0].update(sourceIds=[]),
                       lambda b: b['hypotheses'][0].update(confidence='certain'),
                       lambda b: b.update(sources=[CATALOG[0]]),
                       lambda b: b['sections'][0].update(sourceIds=['test-source']*2),
                       lambda b: b.update(summary='bad\x00text')]:
            body = report()
            mutate(body)
            with self.assertRaises(AnalysisError):
                detail.parse_response(output(body))

    def test_atomic_claim_allows_one_concurrent_generation(self):
        barrier = threading.Barrier(3)
        results, jobs = [], []
        def request():
            barrier.wait()
            results.append(detail.request_detail(self.store, self.target, NOW, jobs.append)[0])
        threads = [threading.Thread(target=request) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [200, 202])
        self.assertEqual(len(jobs), 1)

    def test_context_wrapper_uses_nonblocking_shared_model_lock(self):
        with patch('server.detail_context.build_context',return_value=self.context) as heavy:
            with self.store.analysis_lock():
                with self.assertRaises(BlockingIOError):
                    REAL_BUILD_CONTEXT(self.store,self.parent,NOW)
                heavy.assert_not_called()
            self.assertEqual(REAL_BUILD_CONTEXT(self.store,self.parent,NOW),self.context)
            heavy.assert_called_once()

    def test_schema_extension_preserves_existing_private_records(self):
        with self.store.connect() as db:
            before = [tuple(r) for r in db.execute('SELECT * FROM manual_reports')]
            db.execute('DROP TABLE detail_reports')
        Store(self.path)
        with self.store.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM manual_reports')], before)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


class DetailHttpTests(DetailFixture):
    def setUp(self):
        super().setUp()
        self.server = ThreadedServer(('127.0.0.1', 0), make_handler(self.store, 'i'*32, 'r'*32, 'a'*32))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def fetch(self, path, token=None, body=None, method=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = Request(self.url + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def test_http_roles_syntax_and_explicit_generation(self):
        path = '/api/v1/analysis/detail'
        query = path + '?kind=rolling&reportId=' + self.report_id
        self.assertEqual(self.fetch(query)[0], 401)
        for token in ('r'*32, 'i'*32, 'a'*32):
            code, state = self.fetch(query, token)
            self.assertEqual((code, state['status']), (200, 'available'))
        self.assertEqual(self.fetch(path, 'r'*32, self.target)[0], 401)
        self.assertEqual(self.fetch(path, 'a'*32, {})[0], 400)
        self.assertEqual(self.fetch(path, 'a'*32, method='POST')[0], 413)
        self.assertEqual(self.fetch(path+'?kind=rolling&reportId=x', 'r'*32)[0], 400)
        self.assertEqual(self.fetch(query+'&kind=daily', 'r'*32)[0], 400)
        jobs = []
        original = detail.request_detail
        with patch('server.app.request_detail', side_effect=lambda s, p, n: original(s, p, n, jobs.append, lambda a, b: output())):
            code, state = self.fetch(path, 'a'*32, self.target)
            self.assertEqual((code, state['status']), (202, 'running'))
        self.assertEqual(len(jobs), 1)
        jobs[0]()
        self.assertEqual(self.fetch(query, 'r'*32)[1]['status'], 'ready')

    def test_http_model_or_context_lock_returns_busy_without_build_or_charge(self):
        path='/api/v1/analysis/detail'
        query=path+'?kind=rolling&reportId='+self.report_id
        with patch('server.detail.build_context',wraps=REAL_BUILD_CONTEXT),patch('server.detail_context.build_context',return_value=self.context) as heavy,patch('server.detail.relay_post') as provider:
            with self.store.analysis_lock():
                code,state=self.fetch(query,'r'*32)
                self.assertEqual((code,state['status'],state['eligible']),(200,'available',False))
                code,state=self.fetch(path,'a'*32,self.target)
                self.assertEqual((code,state['status'],state['eligible']),(409,'available',False))
                heavy.assert_not_called()
                provider.assert_not_called()
                self.assertIsNone(self.store.detail_report('rolling',self.report_id,NOW))
            code,state=self.fetch(query,'r'*32)
            self.assertEqual((code,state['eligible']),(200,True))
            heavy.assert_called_once()
            provider.assert_not_called()

    def test_http_busy_retains_the_saved_report(self):
        self.run_request()
        query='/api/v1/analysis/detail?kind=rolling&reportId='+self.report_id
        saved=detail.detail_view(self.store,'rolling',self.report_id,NOW)['report']
        with patch('server.detail.build_context',wraps=REAL_BUILD_CONTEXT),patch('server.detail_context.build_context') as heavy,patch('server.detail.relay_post') as provider:
            with self.store.analysis_lock():
                for code,state in [self.fetch(query,'r'*32),self.fetch('/api/v1/analysis/detail','a'*32,self.target)]:
                    self.assertIn(code,(200,409))
                    self.assertFalse(state['eligible'])
                    self.assertEqual(state['report'],saved)
                heavy.assert_not_called()
                provider.assert_not_called()
