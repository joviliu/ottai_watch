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
    if kind == 'active_calories': value['energyKcal'] = 12.5
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

    def test_native_daily_hr_container_future_end_does_not_create_future_samples(self):
        day_start=NOW-8*60*MINUTE
        day_end=day_start+DAY
        item=record('heart_rate','native-daily',day_start,day_end)
        item['samples']=[{'time':NOW-10*MINUTE,'bpm':65},{'time':NOW-5*MINUTE,'bpm':70}]
        self.ingest(snapshot([item]))
        data=self.store.activity_snapshot(NOW-DAY,NOW)
        view=dashboard_activity(data,NOW-DAY,NOW,NOW)
        self.assertEqual(view['summary']['heartRateSampleCount'],2)
        self.assertEqual(view['kindAvailability']['heart_rate']['lastObservedEndAt'],NOW-5*MINUTE)
        self.assertEqual(view['kindAvailability']['heart_rate']['recordWindowOverlapEndAt'],NOW)
        self.assertEqual(sum(bin['sampleCount'] for bin in view['heartRate']),2)
        self.assertTrue(all(bin['lastSampleAt'] <= NOW for bin in view['heartRate']))
        invalid=copy.deepcopy(item);invalid['samples'].append({'time':NOW+90001,'bpm':80})
        with self.assertRaises(ValueError): validate_activity(snapshot([invalid]),NOW)
        invalid=copy.deepcopy(item);invalid['endAt']=NOW+32*DAY
        with self.assertRaises(ValueError): validate_activity(snapshot([invalid]),NOW)
        # Future-ended sessions are right-censored, with no invented post-exercise effect.
        session=record('exercise','ongoing',NOW-20*MINUTE,NOW+60*MINUTE)
        steps=record('steps','daily-count',day_start,day_end)
        self.ingest(snapshot([session,steps],synced=NOW+1000))
        context=analysis_context(self.store.activity_snapshot(NOW-DAY,NOW),[reading(NOW-10*MINUTE)],NOW-DAY,NOW,NOW)
        event=context['recordedSessions'][0]
        self.assertEqual((event['endBeyondObservationWindow'],event['endCensored'],event['observedEndAt']),(True,True,NOW))
        self.assertIsNone(event['glucoseAfter60m'])
        self.assertIsNone(context['summary']['observedStepTotal'],'future container total must not be prorated')

    def test_clock_tolerance_does_not_create_future_observed_intervals(self):
        session=record('exercise','not-started',NOW+30000,NOW+60*MINUTE)
        steps=record('steps','not-ended',NOW-5*MINUTE,NOW+30000)
        hr=record('heart_rate','clock-skew',NOW-5*MINUTE,NOW+60*MINUTE)
        hr['samples']=[{'time':NOW-MINUTE,'bpm':70},{'time':NOW+30000,'bpm':80}]
        packet=snapshot([session,steps,hr],synced=NOW+60000,end=NOW+60000)
        self.ingest(packet,now=NOW)
        context=analysis_context(self.store.activity_snapshot(NOW-DAY,NOW+60000),[],NOW-DAY,NOW+60000,NOW)
        self.assertEqual(context['recordedSessions'],[],'accepted clock tolerance does not imply session already started')
        self.assertIsNone(context['summary']['observedStepTotal'],'future-ended step container is not fully observed')
        timeline=context['heartRateTimeline']
        self.assertEqual(sum(row[7] for row in timeline['rows']),1)
        self.assertEqual(timeline['lastSampleAt'],NOW-MINUTE,'future timestamp tolerance must not create a future observation')
        self.assertTrue(any('起点' in text for text in context['limitations']))

    def test_hr_timeline_without_exercise_retains_actual_time_and_sample_age(self):
        hr=record('heart_rate','sparse',NOW-DAY,NOW+60*MINUTE)
        hr['samples']=[{'time':NOW-20*MINUTE,'bpm':60},{'time':NOW-10*MINUTE,'bpm':80}]
        self.ingest(snapshot([hr]))
        data=self.store.activity_snapshot(NOW-DAY,NOW)
        context=analysis_context(data,[],NOW-DAY,NOW,NOW+5*MINUTE)
        timeline=context['heartRateTimeline']
        self.assertEqual(context['recordedSessions'],[])
        self.assertEqual(timeline['timeBasis'],'minutes_before_this_periodEnd')
        self.assertEqual(timeline['rows'],[[30,15,20,20,60,60,60,1],[15,0,10,10,80,80,80,1]])
        self.assertEqual(timeline['firstSampleAt'],NOW-20*MINUTE)
        self.assertEqual(timeline['lastSampleAt'],NOW-10*MINUTE)
        self.assertEqual((timeline['lastSampleAgeAtReportMinutes'],timeline['lastSampleAgeAtPeriodEndMinutes']),(15,10))
        self.assertTrue(timeline['lastSampleLocal'].endswith('+08:00'))
        # Missing periods have no artificial zero-valued rows or continuous coverage.
        self.assertEqual(len(timeline['rows']),2)
        session=record('exercise','observed',NOW-25*MINUTE,NOW-5*MINUTE)
        self.ingest(snapshot([hr,session],synced=NOW+1000))
        context=analysis_context(self.store.activity_snapshot(NOW-DAY,NOW),[],NOW-DAY,NOW,NOW+1000)
        self.assertEqual(context['recordedSessions'][0]['observedHeartRateStats'],
                         {'sampleCount':2,'meanBpm':70,'minBpm':60,'maxBpm':80})

    def test_dense_activity_and_year_glucose_model_request_stays_bounded(self):
        from server.analysis import _report_body
        # Two individually bounded daily native snapshots, not one oversized upload.
        records=[]
        for day in range(2):
            start=NOW-(day+1)*DAY
            hr=record('heart_rate','dense'+str(day),start,start+DAY)
            hr['samples']=[{'time':start+i*1000,'bpm':70+i%40} for i in range(86400)]
            records.append(hr)
            for index in range(24):
                records.append(record('exercise','session-%d-%d'%(day,index),start+index*60*MINUTE,start+(index*60+45)*MINUTE))
            for index in range(288):
                records.append(record('steps','steps-%d-%d'%(day,index),start+index*5*MINUTE,start+(index+1)*5*MINUTE))
        state={'status':'available','readableKinds':['exercise','heart_rate','steps'],'lastSyncedAt':NOW}
        activity={'state':state,'records':records,'coverage':{k:[[NOW-2*DAY,NOW]] for k in state['readableKinds']}}
        # Regular daily candidate-like excursions retain realistic un-smoothed glucose variation.
        values=[6.0]*8+[6.3,6.8,7.3,7.9,8.4,8.6,8.4,7.8,7.1,6.5,6.2,6.1,6.0,6.0]+[6.0]*14
        rows=[reading(NOW-365*DAY+i*5*MINUTE,values[i%len(values)]) for i in range(365*288+1)]
        captured=[]
        def invoke(payload,_):captured.append(payload);return response_payload()
        _report_body(rows,NOW,'manual24h','2026-11-10',NOW,invoke,'bounded-test',activity)
        payload=captured[0]
        self.assertLess(len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()),262144)
        observations=json.loads(payload['input'][1]['content'][0]['text'])['observations']
        for name in ('latest24h','previous24h'):
            context=observations['activity'][name]
            self.assertEqual(len(context['heartRateTimeline']['rows']),96)
            self.assertEqual(sum(row[7] for row in context['heartRateTimeline']['rows']),86400)
            self.assertEqual(len(context['recordedSessions']),24)
            self.assertEqual(len(context['shortStepIntervals']),32)
            self.assertTrue(context['shortStepIntervalsTruncated'])
            self.assertEqual(context['stepTimeline']['recordCount'],288)
            self.assertEqual(sum(row[5] for row in context['stepTimeline']['rows']),288)
        self.assertGreater(len(observations['candidateExcursions']['events']),0)

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

    def test_activity_report_times_are_full_shanghai_datetimes(self):
        at=1609459200000  # 2021-01-01T00:00:00Z, not an environment-dependent local timestamp.
        item=record('exercise','dated',at,at+30*MINUTE)
        item['exerciseType']=999
        self.ingest(snapshot([item],start=at-MINUTE,end=at+DAY))
        context=analysis_context(self.store.activity_snapshot(at,at+DAY),[],at,at+DAY,NOW)
        session=context['recordedSessions'][0]
        self.assertEqual(session['startLocal'],'2021-01-01T08:00:00+08:00')
        self.assertEqual(session['endLocal'],'2021-01-01T08:30:00+08:00')
        self.assertEqual((session['timezone'],context['timezone']),('Asia/Shanghai','Asia/Shanghai'))
        self.assertEqual(session['exerciseTypeLabel'],'其他运动（类型代码999）')

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
    def test_activity_rejection_logs_only_static_category(self):
        from server.storage import now_ms
        from server.activity import ActivityValidationError
        now=now_ms()
        item=record('heart_rate','private-id',now-MINUTE,now,modified=0)
        packet=snapshot([item],synced=now,start=now-DAY,end=now)
        with self.assertLogs(level='WARNING') as logs:
            code,body=self.fetch('/api/v1/activity','i'*32,packet)
        self.assertEqual((code,body['reason']),(400,'Invalid activity timestamp: modifiedAt'))
        self.assertIn('activity_validation code=Invalid activity timestamp: modifiedAt',logs.output[0])
        self.assertNotIn('private-id',logs.output[0])
        self.assertEqual(str(ActivityValidationError('untrusted private-id')),'Invalid activity snapshot')

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




def phone_snapshot(rows=None, synced=NOW, status='available'):
    rows=[] if rows is None else copy.deepcopy(rows)
    for row in rows:
        row.update(origin='com.miui.rom',modifiedAt=synced,providerMode=2)
    return dict(source='phone_steps',syncedAt=synced,windowStart=NOW-2*DAY,windowEnd=NOW,
                status=status,readableKinds=['steps'] if status=='available' else [],records=rows,
                revisionBasis='collection_time',originApp={'packageName':'com.miui.rom','versionName':'test','versionCode':1})


class HybridActivityTests(unittest.TestCase):
    setUp=ActivityStorageTests.setUp
    tearDown=ActivityStorageTests.tearDown
    ingest=ActivityStorageTests.ingest

    def test_hybrid_preserves_hc_heart_and_exercise_without_mixing_steps(self):
        hr=record('heart_rate','same-id')
        session=record('exercise','workout')
        self.ingest(snapshot([hr,session]))
        phone=record('steps','same-id',NOW-10*MINUTE,NOW-5*MINUTE);phone['count']=200
        self.ingest(phone_snapshot([phone],NOW+1000))
        result=self.store.activity_snapshot(NOW-DAY,NOW,NOW+1000)
        view=dashboard_activity(result,NOW-DAY,NOW,NOW+1000)
        self.assertEqual(view['source'],'mixed')
        self.assertIsNone(view['origin'])
        self.assertEqual(view['sourceByKind'],{'exercise':'health_connect','heart_rate':'health_connect','steps':'phone_steps','active_calories':'health_connect'})
        self.assertEqual((view['summary']['heartRateSampleCount'],view['summary']['recordedExerciseCount'],view['summary']['observedStepTotal']),(2,1,200))
        self.assertEqual(view['stepIntervals'][0]['origin'],'com.miui.rom')
        self.assertEqual(view['stepIntervals'][0]['providerMode'],2)
        self.assertEqual(view['kindAvailability']['heart_rate']['lastSampleAt'],hr['samples'][-1]['time'])
        context=analysis_context(result,[],NOW-DAY,NOW,NOW+1000)
        self.assertEqual(context['recordedSessions'][0]['origin'],'com.mi.health')
        self.assertEqual(context['shortStepIntervals'][0]['origin'],'com.miui.rom')
        self.assertEqual(context['sourceByKind']['steps'],'phone_steps')
        self.assertEqual(sum(row[7] for row in context['heartRateTimeline']['rows']),2)

    def test_fresh_fine_hc_steps_win_but_phone_wins_over_only_coarse_hc(self):
        hc=record('steps','hc',NOW-10*MINUTE,NOW-5*MINUTE);hc['count']=100
        phone=record('steps','phone',NOW-10*MINUTE,NOW-5*MINUTE);phone['count']=200
        self.ingest(snapshot([hc]));self.ingest(phone_snapshot([phone],NOW+1000))
        selected=self.store.activity_snapshot(NOW-DAY,NOW,NOW+1000)
        self.assertEqual(selected['sourceByKind']['steps'],'health_connect')
        self.assertEqual(dashboard_activity(selected,NOW-DAY,NOW,NOW+1000)['summary']['observedStepTotal'],100)
        hc['startAt']=NOW-DAY;hc['endAt']=NOW;hc['count']=4384;hc['modifiedAt']=NOW+2000
        self.ingest(snapshot([hc],synced=NOW+2000))
        selected=self.store.activity_snapshot(NOW-DAY,NOW,NOW+2000)
        self.assertEqual(selected['sourceByKind']['steps'],'phone_steps')
        self.assertEqual(selected['sourceByKindReason']['steps'],'health_connect_coarse_phone_intervals')
        self.assertEqual(dashboard_activity(selected,NOW-DAY,NOW,NOW+2000)['summary']['observedStepTotal'],200)
        # Coarse phone summaries do not displace a fresh native HC total.
        phone['startAt']=NOW-DAY;phone['endAt']=NOW
        self.ingest(phone_snapshot([phone],NOW+3000))
        self.assertEqual(self.store.activity_snapshot(NOW-DAY,NOW,NOW+3000)['sourceByKind']['steps'],'health_connect')

    def test_fresh_phone_fallback_does_not_mask_stale_or_denied_hc_kind(self):
        hc=record('steps','hc',NOW-10*MINUTE,NOW-5*MINUTE)
        hr=record('heart_rate','hr')
        self.ingest(snapshot([hc,hr]))
        phone=record('steps','phone',NOW-10*MINUTE,NOW-5*MINUTE)
        self.ingest(phone_snapshot([phone],NOW+31*MINUTE))
        selected=self.store.activity_snapshot(NOW-DAY,NOW,NOW+31*MINUTE)
        view=dashboard_activity(selected,NOW-DAY,NOW,NOW+31*MINUTE)
        self.assertEqual(view['sourceByKind']['steps'],'phone_steps')
        self.assertFalse(view['kindAvailability']['steps']['stale'])
        self.assertTrue(view['kindAvailability']['heart_rate']['stale'])
        self.assertEqual(view['kindAvailability']['heart_rate']['lastSampleAt'],hr['samples'][-1]['time'])
        self.ingest(snapshot([],synced=NOW+32*MINUTE,kinds=[],status='permission_denied'))
        view=dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW,NOW+32*MINUTE),NOW-DAY,NOW,NOW+32*MINUTE)
        self.assertEqual(view['sourceByKind']['steps'],'phone_steps')
        self.assertFalse(view['kindAvailability']['heart_rate']['readable'])
        self.assertEqual(view['sourceStates']['health_connect']['status'],'permission_denied')
        self.ingest(phone_snapshot([],NOW+33*MINUTE,status='permission_denied'))
        view=dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW,NOW+33*MINUTE),NOW-DAY,NOW,NOW+33*MINUTE)
        self.assertIsNone(view['summary']['observedStepTotal'])
        self.assertTrue(view['kindAvailability']['steps']['stale'])

    def test_collection_timestamp_only_is_not_new_semantic_phone_snapshot(self):
        self.ingest(snapshot([record('heart_rate','hc')]))
        phone=record('steps','phone',NOW-10*MINUTE,NOW-5*MINUTE)
        self.ingest(phone_snapshot([phone]))
        before=self.store.activity_identity(NOW-2*DAY,NOW,NOW)
        self.assertEqual(self.ingest(phone_snapshot([phone],NOW+1000))['unchanged'],1)
        self.assertEqual(self.store.activity_identity(NOW-2*DAY,NOW,NOW+1000),before)
        phone['count']+=1
        self.assertEqual(self.ingest(phone_snapshot([phone],NOW+2000))['updated'],1)
        self.assertNotEqual(self.store.activity_identity(NOW-2*DAY,NOW,NOW+2000),before)
        # Deleting phone records cannot delete same-ID HC data.
        self.ingest(phone_snapshot([],NOW+3000))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM activity_records WHERE source='health_connect'").fetchone()[0],1)

    def test_two_day_analysis_keeps_one_step_source_for_both_contexts(self):
        hc=record('steps','coarse',NOW-2*DAY,NOW)
        self.ingest(snapshot([hc],start=NOW-2*DAY))
        previous=record('steps','previous',NOW-DAY-10*MINUTE,NOW-DAY-5*MINUTE)
        current=record('steps','current',NOW-10*MINUTE,NOW-5*MINUTE)
        self.ingest(phone_snapshot([previous,current],NOW+1000))
        selected=self.store.activity_snapshot(NOW-2*DAY,NOW,NOW+1000)
        latest=analysis_context(selected,[],NOW-DAY,NOW,NOW+1000)
        prior=analysis_context(selected,[],NOW-2*DAY,NOW-DAY,NOW+1000)
        self.assertEqual(latest['sourceByKind']['steps'],prior['sourceByKind']['steps'])
        self.assertEqual(latest['sourceByKind']['steps'],'phone_steps')
        self.assertEqual(len(latest['shortStepIntervals']),1)
        self.assertEqual(len(prior['shortStepIntervals']),1)
        self.assertEqual(selected['digest'],self.store.activity_identity(NOW-2*DAY,NOW,NOW+1000))

    def test_phone_contract_and_hc_metadata_remain_separate(self):
        good=phone_snapshot([record('steps','phone')])
        self.ingest(good)
        self.assertEqual(self.store.activity_snapshot(NOW-DAY,NOW)['sourceStates']['phone_steps']['revisionBasis'],'collection_time')
        packets=[]
        wrong=phone_snapshot([record('exercise','not-a-phone-sensor')]);packets.append(wrong)
        wrong=copy.deepcopy(good);wrong['records'][0]['origin']='com.mi.health';packets.append(wrong)
        wrong=copy.deepcopy(good);wrong['revisionBasis']='source_modified_at';packets.append(wrong)
        wrong=copy.deepcopy(good);wrong['readableKinds']=['steps','heart_rate'];packets.append(wrong)
        wrong=copy.deepcopy(good);wrong['records'][0]['providerMode']=True;packets.append(wrong)
        for packet in packets:
            with self.assertRaises(ValueError):validate_activity(packet,NOW)

    def test_phone_batch_timeline_keeps_all_352_rows_and_latest_raw_examples(self):
        self.ingest(snapshot([record('heart_rate','hr')]))
        records=[]
        for index in range(352):
            begin=NOW-DAY+index*4*MINUTE
            item=record('steps','phone-step:%03d'%index,begin,begin+(1 if index%2==0 else 30000))
            item['count']=10 if index%2==0 else 50
            records.append(item)
        self.ingest(phone_snapshot(records,NOW+1000))
        snapshot_data=self.store.activity_snapshot(NOW-DAY,NOW,NOW+1000)
        public=dashboard_activity(snapshot_data,NOW-DAY,NOW,NOW+1000)
        self.assertEqual(len(public['stepIntervals']),288)
        self.assertEqual(public['stepIntervals'][-1]['id'],'phone-step:351')
        self.assertEqual(public['stepIntervals'][0]['id'],'phone-step:064')
        self.assertTrue(public['stepIntervalsTruncated'])
        self.assertEqual(public['stepIntervalTotalCount'],352)
        self.assertEqual(sum(row['recordCount'] for row in public['plot']['steps']),352)
        self.assertEqual(sum(row['count'] for row in public['plot']['steps']),176*60)
        self.assertLessEqual(len(public['plot']['steps']),96)
        self.assertEqual(public['plot']['steps'][-1]['lastRecordEndAt'],records[-1]['endAt'])
        self.assertEqual(public['summary']['observedStepTotal'],176*60)
        context=analysis_context(snapshot_data,[],NOW-DAY,NOW,NOW+1000)
        timeline=context['stepTimeline']
        self.assertLessEqual(len(timeline['rows']),96)
        self.assertFalse(timeline['truncated'])
        self.assertEqual((timeline['recordCount'],timeline['groupedRecordCount'],timeline['rawCountSum']),(352,352,176*60))
        self.assertEqual(sum(row[4] for row in timeline['rows']),176*60)
        self.assertEqual(sum(row[5] for row in timeline['rows']),352)
        self.assertEqual(context['shortStepIntervals'][-1]['startAt'],records[-1]['startAt'])
        self.assertEqual(len(context['shortStepIntervals']),32)
        self.assertTrue(context['shortStepIntervalsTruncated'])
        self.assertIn('不能推导步频',timeline['meaning'])
        self.assertFalse(timeline['potentialOverlap'])

    def test_step_timeline_flags_cross_bin_period_future_and_overlap(self):
        first=record('steps','before-start',NOW-DAY-MINUTE,NOW-DAY+MINUTE)
        second=record('steps','cross-bin',NOW-DAY+14*MINUTE,NOW-DAY+16*MINUTE)
        third=record('steps','overlap',NOW-DAY+15*MINUTE,NOW-DAY+17*MINUTE)
        future=record('steps','future-end',NOW-MINUTE,NOW+MINUTE)
        self.ingest(phone_snapshot([first,second,third,future],NOW+1000))
        context=analysis_context(self.store.activity_snapshot(NOW-DAY,NOW,NOW+1000),[],NOW-DAY,NOW,NOW+1000)
        timeline=context['stepTimeline']
        self.assertEqual(timeline['recordCount'],4)
        self.assertEqual(timeline['groupedRecordCount'],3)
        self.assertEqual(timeline['outsideStartWindowRecordCount'],1)
        self.assertEqual(timeline['outsideStartWindowRawCountSum'],1200)
        self.assertEqual(timeline['crossPeriodRecordCount'],2)
        self.assertEqual(timeline['futureEndRecordCount'],1)
        self.assertTrue(timeline['potentialOverlap'])
        self.assertIsNone(timeline['observedStepTotal'])
        self.assertGreaterEqual(sum(row[6] for row in timeline['rows']),2)

    def test_legacy_single_source_migration_preserves_actual_data_and_reports(self):
        from server.activity import canonical
        self.store.ingest([reading(NOW)],NOW)
        self.store.ingest([reading(NOW,6.5)],NOW+1000)
        self.store.claim_report('2026-11-09',NOW)
        self.store.finish_report('2026-11-09',NOW,body={'summary':'preserved'})
        hr=record('heart_rate','legacy',NOW-DAY,NOW+DAY)
        hr['samples']=[{'time':NOW-MINUTE,'bpm':70}]
        with self.store.connect() as db:
            db.executescript("DROP TABLE activity_records; DROP TABLE activity_coverage; DROP TABLE activity_state; "
                "CREATE TABLE activity_records(record_id TEXT PRIMARY KEY,kind TEXT NOT NULL,start_at INTEGER NOT NULL,end_at INTEGER NOT NULL,modified_at INTEGER NOT NULL,body TEXT NOT NULL); "
                "CREATE INDEX activity_interval ON activity_records(start_at,end_at); "
                "CREATE TABLE activity_coverage(kind TEXT NOT NULL,start_at INTEGER NOT NULL,end_at INTEGER NOT NULL,PRIMARY KEY(kind,start_at)); "
                "CREATE TABLE activity_state(source TEXT PRIMARY KEY,synced_at INTEGER NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL,readable_kinds TEXT NOT NULL,window_start INTEGER NOT NULL,window_end INTEGER NOT NULL,last_success_at INTEGER,origin_app TEXT);")
            db.execute('INSERT INTO activity_records VALUES (?,?,?,?,?,?)',(hr['id'],hr['kind'],hr['startAt'],hr['endAt'],hr['modifiedAt'],canonical(hr)))
            db.execute('INSERT INTO activity_coverage VALUES (?,?,?)',('heart_rate',NOW-DAY,NOW))
            db.execute('INSERT INTO activity_state VALUES (?,?,?,?,?,?,?,?,?)',('health_connect',NOW,'legacy-digest','available','["heart_rate"]',NOW-DAY,NOW,NOW,None))
        migrated=Store(self.store.path)
        value=migrated.activity_snapshot(NOW-DAY,NOW,NOW)
        self.assertEqual(value['records'][0],hr)
        self.assertEqual(value['coverage']['heart_rate'],[[NOW-DAY,NOW]])
        self.assertEqual(migrated.latest()['value'],6.5)
        self.assertEqual(migrated.latest_ready_report(),{'summary':'preserved'})
        with migrated.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],1)
            self.assertEqual([r[2] for r in db.execute('PRAGMA index_info(activity_interval)')],['source','start_at','end_at'])
        self.assertEqual(Store(self.store.path).activity_snapshot(NOW-DAY,NOW,NOW)['records'][0],hr)




class ActiveCalorieTests(unittest.TestCase):
    setUp=ActivityStorageTests.setUp
    tearDown=ActivityStorageTests.tearDown
    ingest=ActivityStorageTests.ingest
    kinds=['exercise','heart_rate','steps','active_calories']

    def test_hc_active_energy_is_optional_distinct_and_preserves_provenance(self):
        self.ingest(snapshot([record('heart_rate','hr')]))
        missing=dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW),NOW-DAY,NOW,NOW)
        self.assertIsNone(missing['summary']['observedActiveKcal'])
        self.assertIsNone(missing['summary']['rawActiveKcalSum'])
        self.assertFalse(missing['kindAvailability']['active_calories']['readable'])
        first=record('active_calories','energy1',NOW-10*MINUTE,NOW-5*MINUTE);first['energyKcal']=25.5
        second=record('active_calories','energy2',NOW-5*MINUTE,NOW);second['energyKcal']=34.5
        self.ingest(snapshot([record('heart_rate','hr'),first,second],synced=NOW+1000,kinds=self.kinds))
        self.ingest(phone_snapshot([record('steps','phone',NOW-10*MINUTE,NOW-5*MINUTE)],NOW+2000))
        saved=self.store.activity_snapshot(NOW-DAY,NOW,NOW+2000)
        view=dashboard_activity(saved,NOW-DAY,NOW,NOW+2000)
        self.assertEqual(view['sourceByKind']['active_calories'],'health_connect')
        self.assertEqual((view['summary']['activeCalorieRecordCount'],view['summary']['observedActiveKcal'],view['summary']['rawActiveKcalSum']),(2,60,60))
        self.assertEqual(view['activeCalorieIntervals'][0]['origin'],'com.mi.health')
        self.assertEqual(view['activeCalorieIntervals'][0]['device'],first['device'])
        self.assertEqual(view['summary']['heartRateSampleCount'],2)
        self.assertEqual(view['summary']['stepsSource'],'phone_steps')
        context=analysis_context(saved,[],NOW-DAY,NOW,NOW+2000)
        self.assertEqual(context['activeCalorieTimeline']['recordCount'],2)
        self.assertEqual(context['activeCalorieTimeline']['rawEnergyKcalSum'],60)
        self.assertEqual(context['activeCalorieTimeline']['source'],'health_connect')
        # Revoking only energy access retains cached history but never turns it into a current total.
        self.ingest(snapshot([record('heart_rate','hr')],synced=NOW+3000))
        cached=dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW,NOW+3000),NOW-DAY,NOW,NOW+3000)
        self.assertEqual(cached['summary']['activeCalorieRecordCount'],2)
        self.assertIsNone(cached['summary']['observedActiveKcal'])
        self.assertFalse(cached['kindAvailability']['active_calories']['readable'])

    def test_energy_bounds_and_source_scope_do_not_admit_total_or_basal(self):
        for value in [True,-1,100000.01,float('nan'),float('inf'),'12.5']:
            item=record('active_calories');item['energyKcal']=value
            with self.assertRaises(ValueError):validate_activity(snapshot([item],kinds=self.kinds),NOW)
        item=record('active_calories');item['energyKcal']=0
        self.assertEqual(validate_activity(snapshot([item],kinds=self.kinds),NOW)['records'][0]['energyKcal'],0)
        with self.assertRaises(ValueError):validate_activity(phone_snapshot([item]),NOW)
        for kind in ('total_calories','basal_metabolic_rate'):
            item=record('active_calories');item['kind']=kind
            with self.assertRaises(ValueError):validate_activity(snapshot([item],kinds=self.kinds),NOW)

    def test_energy_overlap_future_and_cross_boundary_are_not_precise_totals(self):
        day=record('active_calories','future-container',NOW-DAY,NOW+DAY);day['energyKcal']=1000
        overlap=record('active_calories','overlap',NOW-MINUTE,NOW);overlap['energyKcal']=10
        self.ingest(snapshot([day,overlap],kinds=self.kinds))
        view=dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW),NOW-DAY,NOW,NOW)
        self.assertIsNone(view['summary']['observedActiveKcal'])
        self.assertEqual(view['summary']['rawActiveKcalSum'],1010)
        self.assertTrue(view['summary']['potentialActiveCalorieOverlap'])
        context=analysis_context(self.store.activity_snapshot(NOW-DAY,NOW),[],NOW-DAY,NOW,NOW)
        timeline=context['activeCalorieTimeline']
        self.assertEqual((timeline['futureEndRecordCount'],timeline['crossPeriodRecordCount']),(1,1))
        self.assertTrue(timeline['potentialOverlap'])
        self.assertIsNone(timeline['observedActiveKcal'])

    def test_public_plot_excludes_coarse_daily_energy_and_keeps_short_start_groups(self):
        coarse=record('active_calories','daily',NOW-DAY,NOW);coarse['energyKcal']=500
        short=record('active_calories','short',NOW-10*MINUTE,NOW-9*MINUTE);short['energyKcal']=5
        cross=record('active_calories','cross-bin',NOW-DAY+14*MINUTE,NOW-DAY+16*MINUTE);cross['energyKcal']=7
        instant=record('active_calories','point',NOW-MINUTE,NOW-MINUTE);instant['energyKcal']=1
        future=record('active_calories','future',NOW-MINUTE,NOW+MINUTE);future['energyKcal']=2
        self.ingest(snapshot([coarse,short,cross,instant,future],kinds=self.kinds))
        public=dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW),NOW-DAY,NOW,NOW)
        plot=public['plot']
        self.assertEqual(plot['intervalMinutes'],15)
        self.assertEqual(plot['coarseActiveCalorieRecordCount'],1)
        self.assertEqual(plot['instantActiveCalorieRecordCount'],1)
        self.assertEqual(plot['futureEndActiveCalorieRecordCount'],1)
        self.assertEqual(sum(row['energyKcal'] for row in plot['activeCalories']),12,'daily total never becomes a fake midnight spike')
        self.assertEqual(sum(row['recordCount'] for row in plot['activeCalories']),2)
        self.assertEqual(sum(row['crossBinRecordCount'] for row in plot['activeCalories']),1)
        self.assertTrue(all(row['source']=='health_connect' for row in plot['activeCalories']))
        self.assertTrue(all(row['lastRecordEndAt']<=NOW for row in plot['activeCalories']))
        self.assertIn('非精确15分钟',plot['meaning'])
        self.assertTrue(any('步频' in text for text in plot['limitations']))

    def test_half_hour_energy_plot_preserves_cadence_and_old_client_contract(self):
        half=record('active_calories','half-hour',NOW-60*MINUTE,NOW-30*MINUTE-1000)
        short=record('active_calories','short',NOW-10*MINUTE,NOW-5*MINUTE)
        crossing_bin=record('active_calories','cross-bin',NOW-DAY+29*MINUTE,NOW-DAY+31*MINUTE)
        coarse=record('active_calories','too-coarse',NOW-180*MINUTE,NOW-149*MINUTE)
        instant=record('active_calories','instant',NOW-MINUTE,NOW-MINUTE)
        future=record('active_calories','future',NOW-MINUTE,NOW+MINUTE)
        crossing_period=record('active_calories','cross-period',NOW-DAY-10*MINUTE,NOW-DAY+10*MINUTE)
        records=[half,short,crossing_bin,coarse,instant,future,crossing_period]
        self.ingest(snapshot(records,start=NOW-2*DAY,kinds=self.kinds))
        saved=self.store.activity_snapshot(NOW-DAY,NOW)
        plot=dashboard_activity(saved,NOW-DAY,NOW,NOW)['plot']
        self.assertEqual(plot['intervalMinutes'],15)
        self.assertTrue(all(row['endAt']-row['startAt']<=15*MINUTE for row in plot['activeCalories']))
        self.assertEqual(sum(row['recordCount'] for row in plot['activeCalories']),2,'old clients retain their15m contract')
        self.assertEqual(plot['activeCalories30mIntervalMinutes'],30)
        self.assertFalse(plot['activeCalories30mTruncated'])
        self.assertEqual(plot['activeCalories30mOmittedRecordCount'],4,'future/cross-period record counted only once')
        rows=plot['activeCalories30m']
        self.assertEqual(sum(row['recordCount'] for row in rows),3)
        self.assertEqual(sum(row['energyKcal'] for row in rows),3*12.5)
        self.assertEqual(sum(row['crossBinRecordCount'] for row in rows),1)
        half_row=next(row for row in rows if row['firstRecordStartAt']==half['startAt'])
        self.assertEqual((half_row['startAt'],half_row['endAt']),(NOW-60*MINUTE,NOW-30*MINUTE))
        self.assertEqual(half_row['lastRecordEndAt'],half['endAt'])
        self.assertEqual(half_row['energyKcal'],half['energyKcal'],'original amount is not split across15m bins')
        context=analysis_context(saved,[],NOW-DAY,NOW,NOW)
        self.assertEqual(context['activeCalorieTimeline']['recordCount'],len(records),'AI retains all original intervals')
        self.assertIn('half-hour',[r['id'] for r in context['activeCalorieExamples']])

    def test_half_hour_energy_plot_is_complete_and_bounded_across_full_day(self):
        records=[record('active_calories','half-%d'%i,NOW-DAY+i*30*MINUTE,NOW-DAY+(i+1)*30*MINUTE-1000)
                 for i in range(48)]
        self.ingest(snapshot(records,kinds=self.kinds))
        plot=dashboard_activity(self.store.activity_snapshot(NOW-DAY,NOW),NOW-DAY,NOW,NOW)['plot']
        self.assertEqual(plot['activeCalories'],[])
        self.assertEqual(len(plot['activeCalories30m']),48)
        self.assertEqual(sum(row['recordCount'] for row in plot['activeCalories30m']),48)
        self.assertEqual(sum(row['energyKcal'] for row in plot['activeCalories30m']),48*12.5)
        self.assertEqual(plot['activeCalories30mOmittedRecordCount'],0)
        self.assertFalse(plot['activeCalories30mTruncated'])

    def test_dense_energy_context_preserves_full_sums_and_model_body_bound(self):
        from server.analysis import _report_body
        records=[]
        for day in range(2):
            start=NOW-(day+1)*DAY
            hr=record('heart_rate','hr'+str(day),start,start+DAY)
            hr['samples']=[{'time':start+i*1000,'bpm':70+i%40} for i in range(86400)]
            records.append(hr)
            for index in range(24):records.append(record('exercise','ex-%d-%d'%(day,index),start+index*60*MINUTE,start+(index*60+45)*MINUTE))
            for index in range(1440):
                energy=record('active_calories','energy-%d-%d'%(day,index),start+index*MINUTE,start+(index+1)*MINUTE)
                energy['energyKcal']=0.25;records.append(energy)
            for index in range(288):records.append(record('steps','step-%d-%d'%(day,index),start+index*5*MINUTE,start+(index+1)*5*MINUTE))
        activity={'state':{'status':'available','readableKinds':self.kinds,'lastSyncedAt':NOW},
                  'records':records,'coverage':{k:[[NOW-2*DAY,NOW]] for k in self.kinds}}
        values=[6.0]*8+[6.3,6.8,7.3,7.9,8.4,8.6,8.4,7.8,7.1,6.5,6.2,6.1,6.0,6.0]+[6.0]*14
        readings=[reading(NOW-365*DAY+i*5*MINUTE,values[i%len(values)]) for i in range(365*288+1)]
        captured=[]
        _report_body(readings,NOW,'manual24h','2026-11-10',NOW,lambda payload,_:captured.append(payload) or response_payload(),'energy-test',activity)
        self.assertLess(len(json.dumps(captured[0],ensure_ascii=False,separators=(',',':')).encode()),262144)
        data=json.loads(captured[0]['input'][1]['content'][0]['text'])['observations']
        for name in ('latest24h','previous24h'):
            context=data['activity'][name]
            timeline=context['activeCalorieTimeline']
            self.assertEqual(len(timeline['rows']),96)
            self.assertEqual(timeline['recordCount'],1440)
            self.assertEqual(timeline['rawEnergyKcalSum'],360)
            self.assertEqual(sum(row[4] for row in timeline['rows']),360)
            self.assertEqual(context['summary']['observedActiveKcal'],360)
            self.assertEqual(len(context['activeCalorieExamples']),32)
            self.assertTrue(context['activeCalorieExamplesTruncated'])
        public=dashboard_activity(activity,NOW-DAY,NOW,NOW)
        self.assertLess(len(json.dumps(public,ensure_ascii=False,separators=(',',':')).encode()),512*1024)
        self.assertEqual(len(public['plot']['activeCalories30m']),48)
        self.assertEqual(sum(row['recordCount'] for row in public['plot']['activeCalories30m']),1440)
        self.assertEqual(sum(row['energyKcal'] for row in public['plot']['activeCalories30m']),360)
        self.assertEqual(len(public['activeCalorieIntervals']),32)
        self.assertTrue(public['activeCalorieIntervalsTruncated'])


if __name__ == '__main__': unittest.main()
