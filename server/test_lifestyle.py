"""Synthetic events, report structure and food-image trust-boundary tests."""
import base64
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import test_server as base
from server.activity import validate_activity
from server.analysis import AnalysisError, SOURCES, _report_body, manual_status, parse_response
from server.app import dashboard
from server.lifestyle import validate_event, context
from server.meals import validate_photo, parse_response as parse_food, request_recognition, job_view
from server.statistics import DAY, MINUTE
from server.storage import Store
from server.test_activity import NOW, record, snapshot

JPEG = '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2P/wAARCAACAAIDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AKAAD//Z'


def event(identifier='event-0001', at=NOW, kind='meal'):
    return {'id':identifier,'type':kind,'at':at,'note':'合成备注','meal':{'foods':'合成餐食','estimatedKcalMin':400,'estimatedKcalMax':600,'source':'manual'}} if kind=='meal' else {'id':identifier,'type':kind,'at':at,'note':'合成备注'}


def photo(identifier='photo-0001', data=JPEG):
    return {'requestId':identifier,'imageBase64':data,'mimeType':'image/jpeg'}


def output(body, **extra):
    return dict(status='completed',output=[{'type':'message','content':[{'type':'output_text','text':json.dumps(body)}]}],**extra)


def concise_report(topic='healthy_reference'):
    return {'summary':'整体较平稳，晚间一次升高回落较慢。','highlights':[{'title':'留意晚间回落','text':'这次升高比近期更宽，值得核对同类餐份量。','severity':'watch','action':'下次记录份量并比较饭后轻走时的变化。'}],
            'evidence':[{'topic':topic,'title':'健康人也有餐后波动','text':'研究描述可解释个体内波动，重点看自身重复形态。','sourceUrl':SOURCES[-1]['url']}],'limitations':[]}


def food_output(**extra):
    return output({'isFoodImage':True,'foods':'合成米饭、蔬菜','estimatedKcalMin':400,'estimatedKcalMax':650},model='gpt-6.1-terra',usage={'input_tokens':1200,'output_tokens':100,'total_tokens':1300,'input_tokens_details':{'cached_tokens':200}},**extra)


class EventTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'test.sqlite3')
    def tearDown(self): self.temp.cleanup()

    def test_validation_bounds_and_editable_meal_range(self):
        saved,expected=validate_event(event(),NOW)
        self.assertIsNone(expected);self.assertEqual(saved['meal']['estimatedKcalMax'],600)
        for mutate in [lambda x:x.update(at=NOW+300001),lambda x:x.update(at=NOW-366*DAY),lambda x:x.update(at=True),lambda x:x.update(type='medication'),lambda x:x.update(note='x'*1001),lambda x:x.update(note='bad\x00'),lambda x:x['meal'].update(estimatedKcalMin=True),lambda x:x['meal'].update(estimatedKcalMax=300),lambda x:x['meal'].update(estimatedKcalMax=None),lambda x:x.update(extra='unknown')]:
            item=event();mutate(item)
            with self.assertRaises(ValueError):validate_event(item,NOW)
        item=event();item['note']='多行\n备注\t可以';self.assertIn('\n',validate_event(item,NOW)[0]['note'])

    def test_conflicts_idempotent_retries_soft_delete_and_identity(self):
        original=self.store.event_identity(NOW-DAY,NOW)
        body,expected=validate_event(event(),NOW);first=self.store.upsert_event(body,expected,NOW)
        self.assertEqual(first,self.store.upsert_event(body,None,NOW+1))
        changed=copy.deepcopy(body);changed['note']='更新'
        with self.assertRaisesRegex(ValueError,'event_conflict'):self.store.upsert_event(changed,None,NOW+1)
        updated=self.store.upsert_event(changed,first['updatedAt'],NOW+1)
        self.assertEqual(updated,self.store.upsert_event(changed,first['updatedAt'],NOW+2))
        with self.assertRaisesRegex(ValueError,'event_conflict'):self.store.delete_event(body['id'],first['updatedAt'],NOW+2)
        self.store.delete_event(body['id'],updated['updatedAt'],NOW+2)
        self.assertEqual(self.store.events(NOW-DAY,NOW),[])
        self.assertEqual(self.store.event_identity(NOW-DAY,NOW),original)
        with self.assertRaisesRegex(ValueError,'event_conflict'):self.store.upsert_event(body,None,NOW+3)

    @patch.dict(os.environ,{'ANALYSIS_ENABLED':'true'})
    def test_events_change_manual_identity_without_bypassing_cooldown(self):
        self.store.ingest([base.reading(NOW-i*5*MINUTE) for i in reversed(range(289))],NOW)
        before=manual_status(self.store,NOW)
        body,_=validate_event(event(at=NOW-60*MINUTE),NOW);saved=self.store.upsert_event(body,None,NOW)
        after=manual_status(self.store,NOW)
        self.assertNotEqual(before['snapshotId'],after['snapshotId'])
        self.assertEqual(self.store.claim_manual(before['snapshotId'],NOW,NOW),'created')
        self.assertFalse(manual_status(self.store,NOW+1)['eligible'])
        self.assertEqual(manual_status(self.store,NOW+1)['status'],'running')

    def test_dashboard_dense_unicode_and_activity_stays_bounded(self):
        for i in range(120):
            item=event('dense-%04d'%i,NOW-i*MINUTE);item['note']='😀'*1000;item['meal']['foods']='🍽'*1000
            self.store.upsert_event(validate_event(item,NOW)[0],None,NOW)
        records=[record('steps','steps-%d'%i,NOW-DAY+i*5*MINUTE,NOW-DAY+(i+1)*5*MINUTE) for i in range(288)]
        records += [record('heart_rate','hr',NOW-DAY,NOW)]
        self.store.ingest_activity(validate_activity(snapshot(records),NOW),NOW)
        data=dashboard(self.store,NOW)
        self.assertEqual(len(data['events']),100);self.assertTrue(data['eventsTruncated'])
        self.assertTrue(data['activity']['plot']['steps'])
        self.assertLess(len(json.dumps(data,ensure_ascii=False).encode()),2000000)
        self.assertEqual(data['events'][-1]['meal']['foods'],'🍽'*1000)

    def test_model_events_are_confirmed_bounded_data_and_evidence_not_repeated(self):
        rows=[base.reading(NOW-i*5*MINUTE) for i in reversed(range(289))]
        markers=[event('meal-%04d'%i,NOW-i*MINUTE) for i in range(30)]
        ctx=context(markers,NOW-DAY,NOW);self.assertEqual(ctx['totalCount'],30);self.assertEqual(len(ctx['events']),24)
        self.assertTrue(all(e['confirmedByUser'] for e in ctx['events']))
        calls=[]
        body=_report_body(rows,NOW,'manual24h','2026-11-10',NOW,lambda p,k:calls.append(p) or output(concise_report()),'test',events=markers,explained_topics=['healthy_reference'])
        self.assertEqual(body['evidence'],[]);self.assertEqual(body['sources'],[])
        self.assertEqual(body['limitations'],[]);self.assertEqual(body['methodVersion'],'cgm-observation-4')
        self.assertEqual(len(body['sections']),1)
        observations=json.loads(calls[0]['input'][1]['content'][0]['text'])['observations']
        self.assertEqual(observations['lifestyle']['latest24h']['totalCount'],30)

    def test_new_report_schema_rejects_excess_and_untrusted_links(self):
        value=concise_report();self.assertEqual(parse_response(output(value))['highlights'][0]['severity'],'watch')
        for mutate in [lambda x:x.update(summary='x'*121),lambda x:x['highlights'][0].update(text='x'*121),lambda x:x['evidence'][0].update(sourceUrl='https://example.invalid/'),lambda x:x.update(highlights=x['highlights']*4),lambda x:x.update(limitations=['x'*101])]:
            data=concise_report();mutate(data)
            with self.assertRaises(AnalysisError):parse_response(output(data))


class EventHttpTests(unittest.TestCase):
    setUp=base.HttpTests.setUp;tearDown=base.HttpTests.tearDown;fetch=base.HttpTests.fetch
    def test_role_separation_create_query_edit_delete(self):
        now=__import__('time').time_ns()//1000000 if hasattr(__import__('time'),'time_ns') else int(__import__('time').time()*1000)
        data=event(at=now)
        self.assertEqual(self.fetch('/api/v1/events','r'*32,data)[0],401)
        code,result=self.fetch('/api/v1/events','a'*32,data);self.assertEqual(code,200)
        self.assertEqual(len(self.fetch('/api/v1/events','a'*32)[1]['events']),1)
        self.assertEqual(self.fetch('/api/v1/dashboard','a'*32)[0],401)
        self.assertEqual(self.fetch('/api/v1/events/delete','r'*32,{'id':data['id']})[0],401)
        self.assertEqual(self.fetch('/api/v1/events/delete','i'*32,{'id':data['id']})[0],409)
        self.assertEqual(self.fetch('/api/v1/events/delete','a'*32,{'id':data['id'],'expectedUpdatedAt':result['event']['updatedAt']})[0],200)
        self.assertEqual(self.fetch('/api/v1/events','r'*32)[1]['events'],[])
        self.assertEqual(self.fetch('/api/v1/events?startAt=x','r'*32)[0],400)
        self.assertEqual(self.fetch('/api/v1/meals/recognize?requestId=photo-0001','r'*32)[0],401)
        self.assertEqual(self.fetch('/api/v1/meals/recognize','r'*32,photo())[0],401)
        self.assertEqual(self.fetch('/api/v1/meals/recognize','i'*32,{'wrong':1})[0],400)


class FoodTests(unittest.TestCase):
    setUp=EventTests.setUp;tearDown=EventTests.tearDown
    def test_jpeg_size_dimensions_metadata_and_type_are_validated(self):
        self.assertEqual(validate_photo(photo())[0],'photo-0001')
        raw=base64.b64decode(JPEG)
        for encoded in ['!!!','x'*1500000,base64.b64encode(b'notjpeg').decode(),base64.b64encode(raw[:2]+b'\xff\xe1\x00\x08Exif00'+raw[2:]).decode()]:
            with self.assertRaises(ValueError):validate_photo(photo(data=encoded))
        oversized=bytearray(raw);at=oversized.index(b'\xff\xc0');oversized[at+7:at+9]=(1025).to_bytes(2,'big')
        with self.assertRaisesRegex(ValueError,'photo_dimensions'):validate_photo(photo(data=base64.b64encode(oversized).decode()))
        bad=photo();bad['mimeType']='image/png'
        with self.assertRaises(ValueError):validate_photo(bad)

    def test_actual_usage_cost_and_missing_inconsistent_usage_remains_unknown(self):
        result=parse_food(food_output());self.assertEqual(result['usage']['inputTokens'],1200)
        self.assertAlmostEqual(result['usage']['estimatedCostUsd'],.00151)
        for mutate in [lambda x:x.pop('usage'),lambda x:x['usage'].update(total_tokens=1),lambda x:x['usage'].update(input_tokens=True),lambda x:x['usage']['input_tokens_details'].update(cached_tokens=9999)]:
            raw=food_output();mutate(raw);data=parse_food(raw)
            self.assertFalse(data['usage']['usageAvailable']);self.assertIsNone(data['usage']['estimatedCostUsd'])
            self.assertTrue(data['recognition']['isFoodImage'])
        raw=food_output();raw['model']='another-model'
        self.assertIsNone(parse_food(raw)['usage']['estimatedCostUsd'])
        self.assertFalse(parse_food(output({'isFoodImage':False,'foods':'bad guess','estimatedKcalMin':4,'estimatedKcalMax':8}))['recognition']['isFoodImage'])

    def test_async_idempotence_same_image_cache_and_no_photo_in_database(self):
        jobs=[];calls=[]
        invoke=lambda p,k:calls.append(p) or food_output()
        self.assertEqual(request_recognition(self.store,photo(),NOW,invoke,jobs.append)[0],202)
        self.assertEqual(request_recognition(self.store,photo(),NOW+1,invoke,jobs.append)[0],202)
        self.assertEqual(len(jobs),1)
        with patch('server.meals.now_ms',return_value=NOW+2):jobs[0]()
        result=job_view(self.store,'photo-0001',NOW+3);self.assertEqual(result['status'],'ready')
        cached=request_recognition(self.store,photo('photo-0002'),NOW+4,invoke,jobs.append)[1]
        self.assertEqual(cached['status'],'ready');self.assertTrue(cached['usage']['cacheHit'])
        self.assertEqual(cached['usage']['totalTokens'],0);self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['reasoning']['effort'],'none')
        with self.store.connect() as db:self.assertNotIn(JPEG,'\n'.join(db.iterdump()))

    def test_unknown_result_is_not_retried_and_food_budget_is_separate(self):
        jobs=[]
        request_recognition(self.store,photo(),NOW,lambda *_:(_ for _ in ()).throw(AnalysisError('relay_network_error')),jobs.append)
        with patch('server.meals.now_ms',return_value=NOW+1):jobs[0]()
        result=request_recognition(self.store,photo(),NOW+2,launch=jobs.append)[1]
        self.assertEqual(result['status'],'error');self.assertEqual(result['outcome'],'uncertain');self.assertEqual(len(jobs),1)
        for i in range(29):
            self.assertEqual(self.store.claim_food('budget-%04d'%i,'digest-%d'%i,NOW+10+i),'created')
            self.store.finish_food('budget-%04d'%i,NOW+10+i,error_code='known_failure')
        with self.assertRaisesRegex(ValueError,'food_daily_limit'):self.store.claim_food('budget-over','new',NOW+100)
        self.assertEqual(self.store.claim_manual('manual-still-independent',NOW,NOW),'created')

    def test_pending_capacity_and_conflicting_identifier_are_bounded(self):
        self.store.claim_food('pending-0001','one',NOW)
        with self.assertRaisesRegex(ValueError,'food_busy'):self.store.claim_food('pending-0002','two',NOW)
        with self.assertRaisesRegex(ValueError,'recognition_conflict'):self.store.claim_food('pending-0001','different',NOW)
        self.assertEqual(self.store.food_job('pending-0001',NOW+151000)['status'],'error')

if __name__=='__main__': unittest.main()
