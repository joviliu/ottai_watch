"""Synthetic Health Connect contract tests; never write production health data."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.activity import (MAX_ACTIVITY_BODY, analysis_context, dashboard_activity,
                             validate_activity)
from server.analysis import manual_status, request_manual, generate_daily
from server.app import dashboard
from server.statistics import DAY, MINUTE
from server.storage import Store
from server import test_server as base_tests
from server.test_server import reading, response_payload

NOW = 1794280000000


def record(kind, identifier='one', start=None, end=None, modified=None):
    start = NOW-2*60*MINUTE if start is None else start
    end = start+30*MINUTE if end is None else end
    value = dict(id=identifier,kind=kind,origin='com.mi.health',startAt=start,endAt=end,
                 modifiedAt=NOW if modified is None else modified,recordingMethod=2,
                 startOffsetSeconds=28800,endOffsetSeconds=28800,
                 device={'manufacturer':'Xiaomi','model':'Synthetic Watch','type':1})
    if kind == 'exercise': value['exerciseType'] = 56
    if kind == 'steps': value['count'] = 1200
    if kind == 'heart_rate': value['samples'] = [{'time':start,'bpm':80},{'time':end,'bpm':120}] if start < end else [{'time':start,'bpm':80}]
    return value


def snapshot(records=None, synced=NOW, start=NOW-DAY, end=NOW, kinds=None, status='available'):
    return dict(source='health_connect',status=status,syncedAt=synced,windowStart=start,windowEnd=end,
                readableKinds=['exercise','heart_rate','steps'] if kinds is None else kinds,
                records=[] if records is None else records,
                originApp={'packageName':'com.mi.health','versionName':'3.59.2','versionCode':359002})


class ActivityStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'activity.sqlite3')

    def tearDown(self): self.temp.cleanup()

    def ingest(self, value, now=None):
        return self.store.ingest_activity(validate_activity(value, now if now is not None else value['syncedAt']),
                                          now if now is not None else value['syncedAt'])

    def test_atomic_idempotence_updates_deletes_and_older_snapshot(self):
        rows = [record('exercise','workout'),record('steps','walk')]
        first = snapshot(rows)
        self.assertEqual(self.ingest(first)['inserted'],2)
        self.assertEqual(self.ingest(first)['status'],'duplicate')
        changed = copy.deepcopy(first);changed['records'][0]['exerciseType']=57
        with self.assertRaisesRegex(ValueError,'snapshot_conflict'): self.ingest(changed)
        changed['syncedAt'] += 1000;changed['records'] = changed['records'][:1]
        changed['records'][0]['modifiedAt'] += 1000
        result = self.ingest(changed)
        self.assertEqual((result['updated'],result['deleted']),(1,1))
        self.assertEqual(self.ingest(first)['status'],'stale_ignored')
        saved = self.store.activity_snapshot(NOW-DAY,NOW)
        self.assertEqual(len(saved['records']),1)
        self.assertEqual(saved['records'][0]['exerciseType'],57)
        self.assertEqual(saved['state']['originApp']['versionCode'],359002)
        # A newer collection carrying an older source revision cannot revert a correction.
        late = copy.deepcopy(first);late['syncedAt'] += 2000;late['records']=late['records'][:1]
        self.assertEqual(self.ingest(late)['unchanged'],1)
        self.assertEqual(self.store.activity_snapshot(NOW-DAY,NOW)['records'][0]['exerciseType'],57)

    def test_start_time_snapshot_preserves_cross_boundary_and_zero_duration(self):
        crossing = record('exercise','cross',NOW-DAY-10*MINUTE,NOW-DAY+10*MINUTE)
        self.ingest(snapshot([crossing],start=NOW-2*DAY))
        # Native readRecords queries START times: absent crossing record must not be deleted.
        self.ingest(snapshot([],synced=NOW+1000))
        self.assertEqual(self.store.activity_snapshot(NOW-DAY,NOW)['records'][0]['id'],'cross')
        with self.assertRaises(ValueError): validate_activity(snapshot([crossing]),NOW)
        zero = record('heart_rate','instant',NOW-DAY,NOW-DAY,modified=NOW+2000)
        self.ingest(snapshot([zero],synced=NOW+2000))
        data = self.store.activity_snapshot(NOW-DAY,NOW)
        self.assertEqual(len(data['records']),2)
        context = analysis_context(data,[],NOW-DAY,NOW,NOW+2000)
        self.assertEqual(context['summary']['heartRateSampleCount'],1)
        self.assertEqual(context['summary']['zeroDurationRecordCount'],1)
        self.assertIsNone(context['recordedSessions'][0]['glucoseBefore30m'])
        # START inside a historic query is valid even if END lies outside the query.
        historic = record('exercise','end-after-window',NOW-2*DAY,NOW-DAY+MINUTE)
        self.assertEqual(len(validate_activity(snapshot([historic],start=NOW-3*DAY,end=NOW-DAY),NOW)['records']),1)

    def test_native_unordered_duplicate_and_empty_hr_samples(self):
        item = record('heart_rate')
        item['samples'] = [{'time':item['endAt'],'bpm':100}, {'time':item['startAt'],'bpm':80},
                           {'time':item['startAt'],'bpm':81}, {'time':item['startAt'],'bpm':80}]
        packet = snapshot([item])
        normalized = validate_activity(packet,NOW)
        self.assertEqual([p['bpm'] for p in normalized['records'][0]['samples']],[80,80,81,100])
        self.ingest(packet)
        packet['records'][0]['samples'].reverse()
        self.assertEqual(self.ingest(packet)['status'],'duplicate','source ordering is not a semantic correction')
        empty = record('heart_rate','empty');empty['samples']=[]
        self.ingest(snapshot([empty],synced=NOW+1000))
        context=analysis_context(self.store.activity_snapshot(NOW-DAY,NOW),[],NOW-DAY,NOW,NOW)
        self.assertEqual(context['summary']['heartRateSampleCount'],0)
        self.assertEqual(context['recordedSessions'],[])

    def test_partial_permissions_and_unavailable_are_not_empty_activity(self):
        self.ingest(snapshot([record('exercise','e'),record('steps','s')]))
        self.ingest(snapshot([],synced=NOW+1000,kinds=['exercise']))
        saved = self.store.activity_snapshot(NOW-DAY,NOW)
        self.assertEqual([r['kind'] for r in saved['records']],['steps'])
        self.ingest(snapshot([],synced=NOW+2000,kinds=[],status='permission_denied'))
        view = dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW),NOW-DAY,NOW,NOW+2000)
        self.assertEqual(view['status'],'permission_denied')
        self.assertTrue(view['stale'])
        self.assertIsNone(view['summary']['recordedExerciseCount'])
        self.assertIsNone(view['summary']['observedStepTotal'])
        self.assertEqual(len(view['stepIntervals']),1,'revocation retains explicitly historical cache')
        self.assertEqual(view['lastSuccessfulSyncAt'],NOW+1000)
        empty = dashboard(Store(Path(self.temp.name)/'empty.sqlite3'),NOW)['activity']
        self.assertEqual(empty['status'],'not_connected')
        self.assertIsNone(empty['summary']['observedStepTotal'])

    def test_validation_rejects_invalid_full_packet_without_partial_write(self):
        good = record('heart_rate')
        mutations = [lambda p:p.update(syncedAt=NOW+90001),
                     lambda p:p.update(windowStart=NOW-32*DAY),
                     lambda p:p.update(source='other'),
                     lambda p:p['originApp'].update(packageName='other'),
                     lambda p:p['records'][0].update(origin='other'),
                     lambda p:p['records'][0].update(kind=[]),
                     lambda p:p['records'][0].update(startOffsetSeconds=64801),
                     lambda p:p['records'][0].update(samples=[{'time':NOW,'bpm':float('nan')}]),
                     lambda p:p['records'][0].update(samples=[{'time':NOW,'bpm':True}]),
                     lambda p:p['records'][0].update(samples=[{'time':NOW+90001,'bpm':90}]),
                     lambda p:p['records'][0].update(route=[{'lat':0,'lon':0}]),
                     lambda p:p['records'].append(copy.deepcopy(p['records'][0]))]
        for mutate in mutations:
            value = snapshot([copy.deepcopy(good)]);mutate(value)
            with self.assertRaises(ValueError): validate_activity(value,NOW)
        self.assertEqual(self.store.activity_snapshot(NOW-DAY,NOW)['records'],[])
        many = copy.deepcopy(good);many['samples'] = [{'time':many['startAt']+i,'bpm':80} for i in range(100001)]
        with self.assertRaises(ValueError): validate_activity(snapshot([many]),NOW)

    def test_native_exercise_labels_never_guess_jetpack_or_unknown_codes(self):
        from server.activity import exercise_type_label
        verified={53:'步行',33:'跑步',34:'跑步机跑步',4:'骑行',5:'固定自行车',
                  48:'开放水域游泳',49:'泳池游泳',45:'力量训练',57:'瑜伽',56:'轮椅活动'}
        for code,label in verified.items(): self.assertEqual(exercise_type_label(code),label)
        self.assertEqual(exercise_type_label(79),'其他运动（类型代码79）','native codes must not use Jetpack walking79')
        known=record('exercise','known');known['exerciseType']=53
        unknown=record('exercise','unknown');unknown['exerciseType']=999
        self.ingest(snapshot([known,unknown]))
        data=self.store.activity_snapshot(NOW-DAY,NOW)
        labels={r['exerciseTypeLabel'] for r in dashboard_activity(data,NOW-DAY,NOW,NOW)['exerciseSessions']}
        self.assertEqual(labels,{'步行','其他运动（类型代码999）'})
        labels={r['exerciseTypeLabel'] for r in analysis_context(data,[],NOW-DAY,NOW,NOW)['recordedSessions']}
        self.assertEqual(labels,{'步行','其他运动（类型代码999）'})

    def test_instant_step_counts_do_not_claim_unique_totals(self):
        one=record('steps','phone',NOW-MINUTE,NOW-MINUTE)
        two=record('steps','watch',NOW-MINUTE,NOW-MINUTE)
        self.ingest(snapshot([one,two]))
        view=dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW),NOW-DAY,NOW,NOW)
        self.assertTrue(view['summary']['potentialStepOverlap'])
        self.assertIsNone(view['summary']['observedStepTotal'])
        self.assertEqual([r['temporalResolution'] for r in view['stepIntervals']],['instant_count','instant_count'])
        context=analysis_context(self.store.activity_snapshot(NOW-DAY,NOW),[],NOW-DAY,NOW,NOW)
        self.assertEqual(context['shortStepIntervals'],[])

    def test_coarse_steps_overlap_hr_duplicates_and_payload_bound(self):
        coarse = record('steps','daily',NOW-DAY,NOW)
        overlap = record('steps','short',NOW-10*MINUTE,NOW)
        hr1 = record('heart_rate','h1',NOW-10*MINUTE,NOW-5*MINUTE)
        hr2 = copy.deepcopy(hr1);hr2['id']='h2';hr2['samples'][1]['bpm']=140
        self.ingest(snapshot([coarse,overlap,hr1,hr2]))
        data = self.store.activity_snapshot(NOW-DAY,NOW)
        view = dashboard_activity(data,NOW-DAY,NOW,NOW)
        self.assertTrue(view['summary']['potentialStepOverlap'])
        self.assertIsNone(view['summary']['observedStepTotal'])
        self.assertEqual(view['summary']['coarseStepRecordCount'],1)
        self.assertEqual(view['summary']['rawHeartRateSampleCount'],4)
        self.assertEqual(view['summary']['heartRateSampleCount'],1)
        self.assertEqual(view['summary']['conflictingHeartRateTimes'],1)
        context = analysis_context(data,[],NOW-DAY,NOW,NOW)
        self.assertEqual(len(context['shortStepIntervals']),1,'daily total is never spread or inferred as activity')
        self.assertEqual(context['recordedSessions'],[],'HR-only does not infer exercise')
        # One-second true sample series is compacted into explicitly labelled 5-minute summaries.
        dense = record('heart_rate','dense',NOW-DAY,NOW)
        dense['samples']=[{'time':NOW-DAY+i*1000,'bpm':60+i%80} for i in range(86400)]
        packet = snapshot([dense],synced=NOW+1000)
        self.assertLess(len(json.dumps(packet).encode()),MAX_ACTIVITY_BODY)
        self.ingest(packet)
        output = dashboard(self.store,NOW+1000)
        self.assertLessEqual(len(output['activity']['heartRate']),288)
        self.assertLess(len(json.dumps(output).encode()),512*1024)
        self.assertIn('not_raw',output['activity']['heartRateRepresentation'])

    @patch.dict(os.environ,{'ANALYSIS_ENABLED':'true'})
    def test_activity_changes_manual_identity_but_refresh_does_not(self):
        self.store.ingest([reading(NOW-DAY+i*5*MINUTE) for i in range(289)],NOW)
        self.ingest(snapshot([record('exercise')]))
        before = manual_status(self.store,NOW)['snapshotId']
        self.assertEqual(self.store.activity_identity(NOW-2*DAY,NOW),self.store.activity_snapshot(NOW-2*DAY,NOW)['digest'])
        self.ingest(snapshot([record('exercise')],synced=NOW+1000))
        self.assertEqual(manual_status(self.store,NOW)['snapshotId'],before)
        changed = record('exercise');changed['exerciseType']=57;changed['modifiedAt']=NOW+2000
        self.ingest(snapshot([changed],synced=NOW+2000))
        self.assertNotEqual(manual_status(self.store,NOW)['snapshotId'],before)
        jobs=[]
        self.assertEqual(request_manual(self.store,NOW,launch=jobs.append)[0],202)
        # Captured activity snapshot is immutable even if a source deletion arrives while queued.
        self.ingest(snapshot([],synced=NOW+3000))
        payloads=[]
        def invoke(payload,_):payloads.append(payload);return response_payload()
        with patch('server.analysis.relay_post',side_effect=invoke): jobs[0]()
        data=json.loads(payloads[0]['input'][1]['content'][0]['text'])['observations']
        self.assertEqual(data['activity']['latest24h']['recordedSessions'][0]['exerciseType'],57)
        self.assertEqual(data['activity']['previous24h']['recordedSessions'],[])
        report=json.loads(self.store.manual_report()['body'])
        self.assertEqual((report['periodStart'],report['periodEnd']),(NOW-DAY,NOW))


class ActivityHttpTests(unittest.TestCase):
    setUp = base_tests.HttpTests.setUp
    tearDown = base_tests.HttpTests.tearDown
    fetch = base_tests.HttpTests.fetch
    def test_activity_write_scope_and_real_collector_schema(self):
        from server.storage import now_ms
        now=now_ms()
        r=record('heart_rate','native-instant',now-MINUTE,now-MINUTE,modified=now)
        payload=snapshot([r],synced=now,start=now-2*DAY,end=now)
        self.assertEqual(self.fetch('/api/v1/activity','r'*32,payload)[0],401)
        self.assertEqual(self.fetch('/api/v1/activity','a'*32,payload)[0],401)
        code,result=self.fetch('/api/v1/activity','i'*32,payload)
        self.assertEqual((code,result['inserted'],result['status']),(200,1,'accepted'))
        self.assertEqual(self.fetch('/api/v1/activity','i'*32,payload)[1]['status'],'duplicate')
        changed=copy.deepcopy(payload);changed['records'][0]['samples'][0]['bpm']=85
        self.assertEqual(self.fetch('/api/v1/activity','i'*32,changed)[0],409)
        changed['syncedAt']=now+1;changed['records'].append(record('steps','bad',now-MINUTE,now,modified=now));changed['records'][-1]['count']=True
        self.assertEqual(self.fetch('/api/v1/activity','i'*32,changed)[0],400)
        self.assertEqual(len(self.store.activity_snapshot(now-DAY,now)['records']),1)
        view=self.fetch('/api/v1/dashboard','r'*32)[1]['activity']
        self.assertEqual(view['originApp']['versionCode'],359002)
        self.assertEqual(view['summary']['heartRateSampleCount'],1)


if __name__ == '__main__': unittest.main()
