import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.detail_context import build_context, meal_profile, activity_window, MAX_CONTEXT_BYTES
from server.statistics import DAY, MINUTE
from server.storage import Store


def reading(at, value=6):
    return {'sourceAt': at, 'value': value, 'trend': '→'}


def meal(at, identifier='MEAL-TEST-0001'):
    return {'id': identifier, 'type': 'meal', 'at': at, 'note': '',
            'meal': {'foods': '合成测试餐食', 'source': 'manual', 'estimatedKcalMin': None, 'estimatedKcalMax': None}}


class DetailContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'isolated.sqlite3')
        self.end = 1794326400000  # Fixed Shanghai midnight.
        self.parent = {'periodStart': self.end - DAY, 'periodEnd': self.end,
                       'kind': 'daily', 'trigger': 'scheduled_daily', 'summary': '合成简报'}
        self.rows = [reading(self.end - 2 * DAY + i * 5 * MINUTE) for i in range(577)]
        self.store.ingest(self.rows, self.end)

    def tearDown(self):
        self.tmp.cleanup()

    def put_record(self, source, record):
        with self.store.connect() as db:
            db.execute('INSERT INTO activity_records VALUES (?,?,?,?,?,?,?)',
                       (source, record['id'], record['kind'], record['startAt'], record['endAt'],
                        self.end, json.dumps(record, ensure_ascii=False)))

    def test_fixed_day_context_has_no_future_and_no_sync_clock_churn(self):
        before = build_context(self.store, self.parent, self.end)
        self.store.ingest([reading(self.end, 20), reading(self.end + MINUTE, 21)], self.end + MINUTE)
        self.store.upsert_event(meal(self.end), None, self.end + MINUTE)
        self.put_record('phone_steps', {'id': 'future', 'kind': 'steps', 'origin': 'com.miui.rom',
                                      'startAt': self.end, 'endAt': self.end + MINUTE, 'count': 100})
        after = build_context(self.store, self.parent, self.end + 20 * MINUTE)
        self.assertEqual(before, after)
        self.assertEqual(after['window']['kind'], 'daily')
        self.assertTrue(all(pair[0] > 0 for pair in after['glucose']['recentReadings']))

    def test_rolling_latest_point_and_mode_focus(self):
        rolling = dict(self.parent, kind='rolling', trigger='manual24h')
        body = build_context(self.store, rolling, self.end + MINUTE)
        self.assertEqual(body['glucose']['recentReadings'][-1][0], 0)
        self.assertNotEqual(body['window']['focus'], build_context(self.store, self.parent, self.end)['window']['focus'])

    def test_real_correction_and_event_change_context(self):
        before = build_context(self.store, self.parent, self.end)
        self.store.ingest([reading(self.end - MINUTE, 8)], self.end)
        self.assertNotEqual(before, build_context(self.store, self.parent, self.end))
        self.store.upsert_event(meal(self.end - 2 * 60 * MINUTE), None, self.end)
        body = build_context(self.store, self.parent, self.end)
        self.assertEqual(len(body['confirmedMeals']), 1)
        self.assertIsNone(body['confirmedMeals'][0]['estimatedKcalMin'])

    def test_event_on_window_start_is_not_in_previous_day(self):
        self.store.upsert_event(meal(self.end - DAY), None, self.end)
        body = build_context(self.store, self.parent, self.end)
        self.assertEqual(len(body['lifestyle']['latest24h']['events']), 1)
        self.assertEqual(len(body['lifestyle']['previous24h']['events']), 0)

    def test_meal_nearest_readings_actual_offsets_and_censoring(self):
        at = self.end - 4 * 60 * MINUTE
        rows = [reading(at + i * 5 * MINUTE, 6 if i <= 0 else 8 if i < 8 else 6) for i in range(-6, 49)]
        body = meal_profile(meal(at), rows, self.end)
        self.assertEqual(body['premealMedian'], 6)
        self.assertEqual(body['observedPeak'], 8)
        self.assertEqual([p['actualMinutes'] for p in body['nearHourReadings']], [60, 120, 180])
        self.assertIsNotNone(body['returnedNearBaselineAt'])
        clipped = meal_profile(meal(at), rows, self.end, at + 45 * MINUTE)
        self.assertTrue(clipped['followupCensored'])
        self.assertEqual(clipped['nearHourReadings'], [])
        self.assertIsNone(clipped['returnedNearBaselineAt'])
        gaps = [r for r in rows if not at + 10 * MINUTE <= r['sourceAt'] <= at + 40 * MINUTE]
        self.assertIsNone(meal_profile(meal(at), gaps, self.end)['returnedNearBaselineAt'])

    def test_unknown_baseline_is_not_zero_and_area_does_not_bridge_gap(self):
        at = self.end - DAY
        no_baseline = meal_profile(meal(at), [reading(at, 7), reading(at + 5 * MINUTE, 8)], self.end)
        self.assertIsNone(no_baseline['premealMedian'])
        self.assertIsNone(no_baseline['observedPositiveAreaMmolMinPerL'])
        rows = [reading(at - 20 * MINUTE), reading(at - 15 * MINUTE), reading(at - 10 * MINUTE),
                reading(at, 5), reading(at + 5 * MINUTE, 7), reading(at + 30 * MINUTE, 7)]
        result = meal_profile(meal(at), rows, self.end)
        self.assertEqual(result['observedPositiveAreaMmolMinPerL'], 1.25)
        self.assertEqual(result['integratedMinutes'], 5)

    def test_hr_container_future_sample_and_duplicate_conflicts(self):
        a = self.end - 60 * MINUTE
        self.put_record('health_connect', {'id': 'hr', 'kind': 'heart_rate', 'origin': 'com.mi.health',
                                         'startAt': a, 'endAt': self.end + DAY,
                                         'samples': [{'time': a, 'bpm': 70}, {'time': self.end, 'bpm': 200}]})
        body = build_context(self.store, self.parent, self.end)
        view = body['activity']['latest24h']
        self.assertEqual(view['heartRateSampleCount'], 1)
        self.assertEqual(view['heartRateTimeline'][0]['meanBpm'], 70)
        with self.store.connect() as db:
            r = json.loads(db.execute("SELECT body FROM activity_records WHERE record_id='hr'").fetchone()[0])
            r['samples'][-1]['bpm'] = 250
            db.execute("UPDATE activity_records SET body=? WHERE record_id='hr'", (json.dumps(r),))
        self.assertEqual(body, build_context(self.store, self.parent, self.end + DAY))

    def test_activity_units_one_step_source_and_cross_boundary_totals(self):
        a = self.end - 60 * MINUTE
        records = [
            ('health_connect', {'id': 'coarse', 'kind': 'steps', 'origin': 'com.mi.health', 'startAt': a, 'endAt': self.end, 'count': 1000}),
            ('phone_steps', {'id': 'fine', 'kind': 'steps', 'origin': 'com.miui.rom', 'startAt': a, 'endAt': a + MINUTE, 'count': 30}),
            ('health_connect', {'id': 'energy', 'kind': 'active_calories', 'origin': 'com.mi.health', 'startAt': a, 'endAt': a + 30 * MINUTE, 'energyKcal': 20}),
            ('health_connect', {'id': 'boundary', 'kind': 'active_calories', 'origin': 'com.mi.health', 'startAt': a, 'endAt': self.end + MINUTE, 'energyKcal': 200})]
        view = activity_window(records, self.end - DAY, self.end)
        self.assertEqual(view['stepsSource'], 'phone_steps')
        self.assertEqual(view['steps']['observedTotal'], 30)
        self.assertEqual(view['activeCalories']['observedTotal'], 20)
        self.assertEqual(view['crossBoundaryOmitted']['active_calories'], 1)

    def test_dense_unicode_context_bounded_without_erasing_storage(self):
        for i in range(80):
            e = meal(self.end - (i + 1) * 20 * MINUTE, 'MEAL-BOUND-%04d' % i)
            e['note'] = '测' * 1000
            e['meal']['foods'] = '食' * 1000
            self.store.upsert_event(e, None, self.end)
        body = build_context(self.store, self.parent, self.end)
        self.assertLessEqual(len(json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()), MAX_CONTEXT_BYTES)
        self.assertLessEqual(len(body['confirmedMeals']), 24)
        self.assertEqual(len(self.store.events(self.end - DAY, self.end)[0]['meal']['foods']), 1000)

    @patch.dict(os.environ, {'DETAIL_PATIENT_CONTEXT': '合成成人背景'})
    def test_private_patient_context_and_no_scheduler_side_effects(self):
        body = build_context(self.store, self.parent, self.end)
        self.assertEqual(body['patient']['providedContext'], '合成成人背景')
        with self.store.connect() as db:
            for table in ('manual_reports', 'reports'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
