import json
import os
import stat
import fcntl
import hashlib
import math
import re
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

TREND = re.compile(r'^(?:\?|[↑↗→↘↓⇈⇊↟↡]{1,32})$')
MAX_BATCH = 1000


def now_ms():
    return int(time.time() * 1000)


def validate_batch(payload, now):
    if not isinstance(payload, dict) or set(payload) != {'readings'}:
        raise ValueError('Expected readings object')
    items = payload['readings']
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH:
        raise ValueError('Expected 1–1000 readings')
    normalized = []
    for item in items:
        if not isinstance(item, dict) or set(item) - {'value', 'sourceAt', 'trend', 'historical'}:
            raise ValueError('Invalid reading fields')
        value, at, trend = item.get('value'), item.get('sourceAt'), item.get('trend')
        if type(value) not in (int, float) or not 0 < value <= 60 or not math.isfinite(value):
            raise ValueError('Invalid mmol/L value')
        if type(at) is not int or not 0 < at <= now + 90000:
            raise ValueError('Invalid sourceAt timestamp')
        if not isinstance(trend, str) or not TREND.fullmatch(trend):
            raise ValueError('Invalid trend')
        if 'historical' in item and type(item['historical']) is not bool:
            raise ValueError('Invalid historical flag')
        normalized.append({'sourceAt': at, 'value': float(value), 'trend': trend,
                           'historical': item.get('historical', False)})
    return normalized


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS readings (
                    source_at INTEGER PRIMARY KEY, value REAL NOT NULL, trend TEXT NOT NULL,
                    received_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id INTEGER PRIMARY KEY, source_at INTEGER NOT NULL,
                    old_value REAL NOT NULL, old_trend TEXT NOT NULL,
                    new_value REAL NOT NULL, new_trend TEXT NOT NULL, changed_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity_records (
                    source TEXT NOT NULL, record_id TEXT NOT NULL, kind TEXT NOT NULL,
                    start_at INTEGER NOT NULL, end_at INTEGER NOT NULL,
                    modified_at INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(source,record_id)
                );
                CREATE TABLE IF NOT EXISTS activity_state (
                    source TEXT PRIMARY KEY, synced_at INTEGER NOT NULL, digest TEXT NOT NULL,
                    status TEXT NOT NULL, readable_kinds TEXT NOT NULL,
                    window_start INTEGER NOT NULL, window_end INTEGER NOT NULL,
                    last_success_at INTEGER, origin_app TEXT, revision_basis TEXT
                );
                CREATE TABLE IF NOT EXISTS activity_coverage (
                    source TEXT NOT NULL, kind TEXT NOT NULL, start_at INTEGER NOT NULL, end_at INTEGER NOT NULL,
                    PRIMARY KEY(source,kind,start_at)
                );
                CREATE TABLE IF NOT EXISTS lifestyle_events (
                    event_id TEXT PRIMARY KEY, at INTEGER NOT NULL, kind TEXT NOT NULL,
                    body TEXT NOT NULL, updated_at INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS lifestyle_at ON lifestyle_events(at);
                CREATE TABLE IF NOT EXISTS evidence_topics (topic TEXT PRIMARY KEY, seen_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS food_jobs (
                    request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, status TEXT NOT NULL,
                    started_at INTEGER NOT NULL, finished_at INTEGER, body TEXT, error_code TEXT,
                    reserved INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS manual_reports (
                    snapshot_id TEXT PRIMARY KEY, window_end INTEGER NOT NULL,
                    status TEXT NOT NULL, started_at INTEGER NOT NULL, finished_at INTEGER,
                    body TEXT, error_code TEXT
                );
                CREATE TABLE IF NOT EXISTS reports (
                    report_date TEXT PRIMARY KEY, status TEXT NOT NULL,
                    started_at INTEGER NOT NULL, finished_at INTEGER,
                    body TEXT, error_code TEXT
                );
                CREATE TABLE IF NOT EXISTS detail_reports (
                    job_id TEXT PRIMARY KEY, report_id TEXT NOT NULL, kind TEXT NOT NULL,
                    context_digest TEXT NOT NULL, request_key TEXT NOT NULL, status TEXT NOT NULL, started_at INTEGER NOT NULL,
                    finished_at INTEGER, period_start INTEGER NOT NULL, period_end INTEGER NOT NULL,
                    parent_body TEXT NOT NULL, context_body TEXT NOT NULL, body TEXT, error_code TEXT
                );
                CREATE INDEX IF NOT EXISTS detail_parent ON detail_reports(kind,report_id,started_at);
            ''')
            # Migrate only activity tables; glucose, revisions and reports are untouched.
            # BEGIN rechecks under the write lock if API and timer start together.
            db.execute('BEGIN IMMEDIATE')
            columns = [r[1] for r in db.execute('PRAGMA table_info(activity_state)').fetchall()]
            if 'origin_app' not in columns:
                db.execute('ALTER TABLE activity_state ADD COLUMN origin_app TEXT')
            if 'revision_basis' not in columns:
                db.execute('ALTER TABLE activity_state ADD COLUMN revision_basis TEXT')
            if 'source' not in [r[1] for r in db.execute('PRAGMA table_info(activity_records)').fetchall()]:
                db.execute('ALTER TABLE activity_records RENAME TO activity_records_v1')
                db.execute("CREATE TABLE activity_records (source TEXT NOT NULL, record_id TEXT NOT NULL, kind TEXT NOT NULL, start_at INTEGER NOT NULL, end_at INTEGER NOT NULL, modified_at INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(source,record_id))")
                db.execute("INSERT INTO activity_records SELECT 'health_connect',record_id,kind,start_at,end_at,modified_at,body FROM activity_records_v1")
                db.execute('DROP TABLE activity_records_v1')
            db.execute('CREATE INDEX IF NOT EXISTS activity_interval ON activity_records(source,start_at,end_at)')
            if 'source' not in [r[1] for r in db.execute('PRAGMA table_info(activity_coverage)').fetchall()]:
                db.execute('ALTER TABLE activity_coverage RENAME TO activity_coverage_v1')
                db.execute('CREATE TABLE activity_coverage (source TEXT NOT NULL, kind TEXT NOT NULL, start_at INTEGER NOT NULL, end_at INTEGER NOT NULL, PRIMARY KEY(source,kind,start_at))')
                db.execute("INSERT INTO activity_coverage SELECT 'health_connect',kind,start_at,end_at FROM activity_coverage_v1")
                db.execute('DROP TABLE activity_coverage_v1')
        Path(self.path).chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, items, now):
        counts = {'accepted': len(items), 'inserted': 0, 'corrected': 0, 'unchanged': 0}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for item in items:
                at, value, trend = item['sourceAt'], item['value'], item['trend']
                old = db.execute('SELECT value,trend FROM readings WHERE source_at=?', (at,)).fetchone()
                if old is None:
                    db.execute('INSERT INTO readings VALUES (?,?,?,?,?)', (at, value, trend, now, now))
                    counts['inserted'] += 1
                elif item.get('historical') or (old['value'] == value and old['trend'] == trend):
                    counts['unchanged'] += 1
                else:
                    db.execute('INSERT INTO revisions(source_at,old_value,old_trend,new_value,new_trend,changed_at) VALUES (?,?,?,?,?,?)',
                               (at, old['value'], old['trend'], value, trend, now))
                    db.execute('UPDATE readings SET value=?,trend=?,updated_at=? WHERE source_at=?', (value, trend, now, at))
                    counts['corrected'] += 1
        return counts

    def readings(self, start=0, end=None):
        with self.connect() as db:
            rows = db.execute('SELECT source_at,value,trend FROM readings WHERE source_at>=? AND source_at<=? ORDER BY source_at',
                              (start, end if end is not None else 2**63 - 1)).fetchall()
        return [{'sourceAt': r['source_at'], 'value': r['value'], 'trend': r['trend']} for r in rows]

    def latest(self):
        with self.connect() as db:
            r = db.execute('SELECT source_at,value,trend FROM readings ORDER BY source_at DESC LIMIT 1').fetchone()
        return None if r is None else {'sourceAt': r['source_at'], 'value': r['value'], 'trend': r['trend']}

    def span(self):
        with self.connect() as db:
            r = db.execute('SELECT MIN(source_at),MAX(source_at),COUNT(*) FROM readings').fetchone()
        return {'firstAt': r[0], 'lastAt': r[1], 'sampleCount': r[2]}

    def ingest_activity(self, snapshot, now):
        """A complete native START-time read window is reconciled in one SQLite transaction.

        Each source is independent. Older uploads never delete newer observations, and a
        changed source record never regresses to an older modifiedAt revision.
        """
        from .activity import canonical, SOURCE_REVISION_BASIS
        source = snapshot['source']
        digest = hashlib.sha256(canonical(snapshot).encode('utf-8')).hexdigest()
        counts = dict(accepted=len(snapshot['records']), inserted=0, updated=0, deleted=0, unchanged=0)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = db.execute('SELECT * FROM activity_state WHERE source=?', (snapshot['source'],)).fetchone()
            if state is not None:
                if snapshot['syncedAt'] < state['synced_at']:
                    return dict(counts, status='stale_ignored')
                if snapshot['syncedAt'] == state['synced_at']:
                    if digest != state['digest']:
                        raise ValueError('snapshot_conflict')
                    return dict(counts, unchanged=len(snapshot['records']), status='duplicate')
            if snapshot['status'] == 'available':
                old_rows = db.execute('SELECT * FROM activity_records WHERE source=? AND start_at>=? AND start_at<?',
                                      (source, snapshot['windowStart'], snapshot['windowEnd'])).fetchall()
                present = {row['id'] for row in snapshot['records']}
                for row in old_rows:
                    if row['kind'] in snapshot['readableKinds'] and row['record_id'] not in present and row['modified_at'] <= snapshot['syncedAt']:
                        db.execute('DELETE FROM activity_records WHERE source=? AND record_id=?', (source,row['record_id']))
                        counts['deleted'] += 1
                for record in snapshot['records']:
                    body = canonical(record)
                    old = db.execute('SELECT * FROM activity_records WHERE source=? AND record_id=?', (source,record['id'])).fetchone()
                    if old is None:
                        db.execute('INSERT INTO activity_records VALUES (?,?,?,?,?,?,?)',
                                   (source,record['id'], record['kind'], record['startAt'], record['endAt'], record['modifiedAt'], body))
                        counts['inserted'] += 1
                    elif (record['modifiedAt'] < old['modified_at'] or old['body'] == body or
                          source == 'phone_steps' and
                          {k:v for k,v in json.loads(old['body']).items() if k!='modifiedAt'} ==
                          {k:v for k,v in record.items() if k!='modifiedAt'}):
                        counts['unchanged'] += 1
                    else:
                        db.execute('UPDATE activity_records SET kind=?,start_at=?,end_at=?,modified_at=?,body=? WHERE source=? AND record_id=?',
                                   (record['kind'], record['startAt'], record['endAt'], record['modifiedAt'], body, source,record['id']))
                        counts['updated'] += 1
                # Union the windows successfully read for each kind. This describes
                # query availability, never continuous wear or HR sample coverage.
                for kind in snapshot['readableKinds']:
                    a, b = snapshot['windowStart'], snapshot['windowEnd']
                    overlaps = db.execute('SELECT start_at,end_at FROM activity_coverage WHERE source=? AND kind=? AND start_at<=? AND end_at>=?', (source,kind,b,a)).fetchall()
                    for prior in overlaps:
                        a, b = min(a,prior['start_at']), max(b,prior['end_at'])
                    db.execute('DELETE FROM activity_coverage WHERE source=? AND kind=? AND start_at<=? AND end_at>=?', (source,kind,b,a))
                    db.execute('INSERT INTO activity_coverage VALUES (?,?,?,?)', (source,kind,a,b))
            last_success = snapshot['syncedAt'] if snapshot['status']=='available' else (state['last_success_at'] if state else None)
            db.execute('INSERT OR REPLACE INTO activity_state VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (snapshot['source'],snapshot['syncedAt'],digest,snapshot['status'],canonical(snapshot['readableKinds']),
                        snapshot['windowStart'],snapshot['windowEnd'],last_success,canonical(snapshot.get('originApp')),SOURCE_REVISION_BASIS[source]))
        return dict(counts, status='accepted')

    def _activity_selection(self, db, start, end, now):
        from .activity import SOURCE_ORIGINS, SOURCE_REVISION_BASIS
        states = {source: {'source':source,'status':'not_connected','readableKinds':[],
                           'lastSyncedAt':None,'lastSuccessfulSyncAt':None,'stale':True}
                  for source in SOURCE_ORIGINS}
        for row in db.execute('SELECT * FROM activity_state'):
            if row['source'] not in states:
                continue
            states[row['source']].update(status=row['status'],readableKinds=json.loads(row['readable_kinds']),
                lastSyncedAt=row['synced_at'],lastSuccessfulSyncAt=row['last_success_at'],
                stale=row['status']!='available' or now-row['synced_at']>=30*60000,
                windowStart=row['window_start'],windowEnd=row['window_end'],
                originApp=json.loads(row['origin_app']) if row['origin_app'] else None,
                revisionBasis=row['revision_basis'] or SOURCE_REVISION_BASIS[row['source']])
        step_rows = db.execute("SELECT source,start_at,end_at FROM activity_records WHERE kind='steps' AND start_at<? AND (end_at>? OR (start_at=end_at AND start_at>=?))",(end,start,start)).fetchall()
        records = {source:[r for r in step_rows if r['source']==source and r['start_at']<=min(end,now)] for source in states}
        def fresh(source):
            value=states[source]
            return value['status']=='available' and 'steps' in value['readableKinds'] and not value['stale']
        def fine(source):
            return any(0 < r['end_at']-r['start_at'] <= 15*60000 for r in records[source])
        if fresh('health_connect') and records['health_connect']:
            if not fine('health_connect') and fresh('phone_steps') and fine('phone_steps'):
                chosen,reason='phone_steps','health_connect_coarse_phone_intervals'
            else:
                chosen,reason='health_connect','health_connect_fresh_records'
        elif fresh('phone_steps') and records['phone_steps']:
            chosen,reason='phone_steps','phone_fresh_records'
        elif any(records.values()):
            chosen=max((source for source in states if records[source]),
                       key=lambda source:(states[source]['lastSuccessfulSyncAt'] or 0,source))
            reason='cached_records_only_no_fresh_readable_source'
        else:
            chosen='phone_steps' if states['phone_steps']['lastSyncedAt'] is not None else 'health_connect'
            reason='no_step_records'
        selected={'exercise':'health_connect','heart_rate':'health_connect','steps':chosen,'active_calories':'health_connect'}
        reasons={'exercise':'health_connect_only','heart_rate':'health_connect_only','steps':reason,'active_calories':'health_connect_only'}
        return states,selected,reasons

    def activity_snapshot(self, start, end, now=None):
        now=end if now is None else now
        with self.connect() as db:
            db.execute('BEGIN')
            states,selected,reasons=self._activity_selection(db,start,end,now)
            identity=self._activity_identity(db,start,end,now,selection=(states,selected,reasons))
            rows=db.execute('SELECT source,kind,body FROM activity_records WHERE start_at<? AND (end_at>? OR (start_at=end_at AND start_at>=?)) ORDER BY start_at,record_id',(end,start,start)).fetchall()
            records=[json.loads(r['body']) for r in rows if selected.get(r['kind'])==r['source']]
            coverage={kind:[] for kind in selected}
            for r in db.execute('SELECT * FROM activity_coverage WHERE start_at<? AND end_at>? ORDER BY start_at',(end,start)):
                if selected.get(r['kind'])==r['source']:
                    coverage[r['kind']].append([max(start,r['start_at']),min(end,r['end_at'])])
        used={selected[kind] for kind in selected if states[selected[kind]]['status']!='not_connected'}
        source='mixed' if len(used)>1 else next(iter(used)) if used else 'health_connect'
        readable=[kind for kind in selected if states[selected[kind]]['status']=='available' and kind in states[selected[kind]]['readableKinds']]
        status='available' if readable else states[selected['steps']]['status']
        syncs=[state['lastSyncedAt'] for state in states.values() if state['lastSyncedAt'] is not None]
        success=[state['lastSuccessfulSyncAt'] for state in states.values() if state['lastSuccessfulSyncAt'] is not None]
        state={'source':source,'status':status,'readableKinds':readable,'lastSyncedAt':max(syncs) if syncs else None,
               'lastSuccessfulSyncAt':max(success) if success else None,
               'originApp':states[source].get('originApp') if source in states else None,
               'windowStart':start,'windowEnd':end}
        return {'state':state,'sourceStates':states,'sourceByKind':selected,'sourceByKindReason':reasons,
                'records':records,'coverage':coverage,'digest':identity}

    def _activity_identity(self, db, start, end, now, selection=None):
        """Only selected records/coverage count; source query timestamps do not."""
        from .activity import canonical
        states,selected,reasons=selection or self._activity_selection(db,start,end,now)
        digest=hashlib.sha256()
        for kind,source in sorted(selected.items()):
            state=states[source]
            digest.update(canonical([kind,source,state['status'],kind in state['readableKinds'],state['stale']]).encode())
            for r in db.execute('SELECT start_at,end_at FROM activity_coverage WHERE source=? AND kind=? AND start_at<? AND end_at>? ORDER BY start_at',(source,kind,end,start)):
                digest.update(canonical([max(start,r['start_at']),min(end,r['end_at'])]).encode())
            for r in db.execute('SELECT body FROM activity_records WHERE source=? AND kind=? AND start_at<? AND (end_at>? OR (start_at=end_at AND start_at>=?)) ORDER BY start_at,record_id',(source,kind,end,start,start)):
                digest.update(b'\0');digest.update(r['body'].encode('utf-8'))
        return digest.hexdigest()

    def activity_identity(self, start, end, now=None):
        with self.connect() as db:
            db.execute('BEGIN')
            return self._activity_identity(db,start,end,end if now is None else now)

    def events(self, start, end, limit=1000):
        with self.connect() as db:
            rows = db.execute('SELECT body,updated_at FROM lifestyle_events WHERE deleted=0 AND at>=? AND at<=? ORDER BY at DESC,event_id LIMIT ?', (start,end,limit)).fetchall()
        return [dict(json.loads(r['body']), updatedAt=r['updated_at']) for r in reversed(rows)]

    def event_snapshot(self, start, end):
        with self.connect() as db:
            rows = db.execute('SELECT body,updated_at FROM lifestyle_events WHERE deleted=0 AND at>=? AND at<=? ORDER BY event_id', (start,end)).fetchall()
        digest = hashlib.sha256(('['+','.join(r['body'] for r in rows)+']').encode('utf-8')).hexdigest()
        events = sorted([dict(json.loads(r['body']),updatedAt=r['updated_at']) for r in rows], key=lambda e:(e['at'],e['id']))
        return {'events':events,'digest':digest}

    def event_identity(self, start, end):
        return self.event_snapshot(start,end)['digest']

    def upsert_event(self, event, expected, now):
        from .lifestyle import canonical
        body = canonical(event)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM lifestyle_events WHERE event_id=?', (event['id'],)).fetchone()
            if old and not old['deleted'] and old['body'] == body:
                return dict(event, updatedAt=old['updated_at'])
            if old and expected != old['updated_at'] or not old and expected is not None:
                raise ValueError('event_conflict')
            if not old and db.execute('SELECT COUNT(*) FROM lifestyle_events WHERE deleted=0 AND at>=? AND at<?', (event['at']-86400000,event['at']+86400000)).fetchone()[0] >= 500:
                raise ValueError('event_limit')
            updated = max(now, old['updated_at']+1 if old else now)
            db.execute('INSERT OR REPLACE INTO lifestyle_events VALUES (?,?,?,?,?,0)', (event['id'],event['at'],event['type'],body,updated))
        return dict(event, updatedAt=updated)

    def delete_event(self, event_id, expected, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM lifestyle_events WHERE event_id=?', (event_id,)).fetchone()
            if not old or old['deleted']:
                return
            if expected != old['updated_at']:
                raise ValueError('event_conflict')
            db.execute('UPDATE lifestyle_events SET deleted=1,updated_at=? WHERE event_id=?', (max(now,old['updated_at']+1),event_id))

    def recent_evidence_topics(self):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM (SELECT body,finished_at FROM reports WHERE status='ready' UNION ALL SELECT body,finished_at FROM manual_reports WHERE status='ready') ORDER BY finished_at DESC LIMIT 12").fetchall()
            topics = {r[0] for r in db.execute('SELECT topic FROM evidence_topics')}
            for row in rows:
                try:
                    report = json.loads(row['body'])
                    topics.update(e['topic'] for e in report.get('evidence',[]) if isinstance(e,dict) and isinstance(e.get('topic'),str))
                    prose=json.dumps({'summary':report.get('summary',''),'sections':report.get('sections',[])},ensure_ascii=False).lower()
                    if 'shah' in prose:
                        topics.add('healthy_reference')
                except (TypeError,ValueError,KeyError):
                    pass
            for topic in topics:
                db.execute('INSERT OR IGNORE INTO evidence_topics VALUES (?,?)', (topic,now_ms()))
        return sorted(topics)

    def _save_evidence_topics(self, db, body, now):
        for item in (body or {}).get('evidence',[]):
            db.execute('INSERT OR IGNORE INTO evidence_topics VALUES (?,?)', (item['topic'],now))

    def food_job(self, request_id, now):
        with self.connect() as db:
            db.execute("UPDATE food_jobs SET status='error',finished_at=?,error_code='provider_uncertain' WHERE request_id=? AND status='running' AND started_at<?", (now,request_id,now-150000))
            row = db.execute('SELECT * FROM food_jobs WHERE request_id=?', (request_id,)).fetchone()
        return dict(row) if row else None

    def claim_food(self, request_id, digest, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM food_jobs WHERE request_id=?', (request_id,)).fetchone()
            if old:
                if old['digest'] != digest:
                    raise ValueError('recognition_conflict')
                return 'existing'
            cached = db.execute("SELECT body FROM food_jobs WHERE digest=? AND status='ready' AND finished_at>? ORDER BY finished_at DESC LIMIT 1", (digest,now-86400000)).fetchone()
            if cached:
                body = json.loads(cached['body'])
                body['usage'] = dict(body['usage'], inputTokens=0,outputTokens=0,totalTokens=0,cachedInputTokens=0,estimatedCostUsd=0,cacheHit=True,usageAvailable=True)
                db.execute("INSERT INTO food_jobs VALUES (?,?,'ready',?,?,?,NULL,0)", (request_id,digest,now,now,json.dumps(body,ensure_ascii=False)))
                return 'cached'
            if db.execute("SELECT 1 FROM food_jobs WHERE status='running' AND started_at>?",(now-150000,)).fetchone():
                raise ValueError('food_busy')
            day_start = ((now+8*3600000)//86400000)*86400000-8*3600000
            if db.execute('SELECT COUNT(*) FROM food_jobs WHERE reserved=1 AND started_at>=? AND started_at<?',(day_start,day_start+86400000)).fetchone()[0] >= 30:
                raise ValueError('food_daily_limit')
            db.execute("INSERT INTO food_jobs(request_id,digest,status,started_at) VALUES (?,?,'running',?)", (request_id,digest,now))
        return 'created'

    def finish_food(self, request_id, now, body=None, error_code=None):
        with self.connect() as db:
            db.execute('UPDATE food_jobs SET status=?,finished_at=?,body=?,error_code=? WHERE request_id=? AND status=?', ('error' if error_code else 'ready',now,json.dumps(body,ensure_ascii=False) if body else None,error_code,request_id,'running'))

    def claim_report(self, day, now):
        """Unique day is also the network-call lock; failed calls are not auto-retried."""
        with self.connect() as db:
            result = db.execute('INSERT OR IGNORE INTO reports(report_date,status,started_at) VALUES (?,?,?)', (day, 'running', now))
            return result.rowcount == 1

    def finish_report(self, day, now, body=None, error_code=None):
        with self.connect() as db:
            if body and not error_code:
                self._save_evidence_topics(db, body, now)
            db.execute('UPDATE reports SET status=?,finished_at=?,body=?,error_code=? WHERE report_date=?',
                       ('error' if error_code else 'ready', now, json.dumps(body, ensure_ascii=False) if body else None, error_code, day))

    def report(self):
        with self.connect() as db:
            r = db.execute('SELECT * FROM reports ORDER BY report_date DESC LIMIT 1').fetchone()
        return dict(r) if r else None

    def latest_ready_report(self):
        with self.connect() as db:
            r = db.execute("SELECT body FROM reports WHERE status='ready' ORDER BY report_date DESC LIMIT 1").fetchone()
        return json.loads(r['body']) if r else None

    def manual_report(self, snapshot_id=None, ready_only=False):
        with self.connect() as db:
            clauses, params = [], []
            if snapshot_id:
                clauses.append('snapshot_id=?'); params.append(snapshot_id)
            if ready_only:
                clauses.append("status='ready'")
            where = ' WHERE '+' AND '.join(clauses) if clauses else ''
            row = db.execute('SELECT * FROM manual_reports'+where+' ORDER BY started_at DESC LIMIT 1', params).fetchone()
        return dict(row) if row else None

    def claim_manual(self, snapshot_id, window_end, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM manual_reports WHERE snapshot_id=?', (snapshot_id,)).fetchone():
                return 'existing'
            if db.execute("SELECT 1 FROM detail_reports WHERE status='running' AND started_at>=?", (now-180000,)).fetchone():
                return 'busy'
            latest = db.execute('SELECT MAX(started_at) FROM manual_reports').fetchone()[0]
            if latest is not None and now-latest < 30*60*1000:
                return 'cooldown'
            db.execute('INSERT INTO manual_reports(snapshot_id,window_end,status,started_at) VALUES (?,?,?,?)',
                       (snapshot_id, window_end, 'running', now))
            return 'created'

    def _expire_details(self, db, now):
        db.execute("UPDATE detail_reports SET status='error',finished_at=?,error_code='detail_uncertain' WHERE status='running' AND started_at<?", (now,now-180000))

    def active_detail(self, now):
        with self.connect() as db:
            self._expire_details(db,now)
            return db.execute("SELECT 1 FROM detail_reports WHERE status='running' LIMIT 1").fetchone() is not None

    def analysis_busy(self, now):
        with self.connect() as db:
            self._expire_details(db,now)
            return any(db.execute("SELECT 1 FROM %s WHERE status='running' AND started_at>=? LIMIT 1" % table,(now-180000,)).fetchone() is not None for table in ('detail_reports','manual_reports','reports'))

    def detail_report(self, kind, report_id, now, job_id=None, request_key=None, ready_only=False):
        with self.connect() as db:
            self._expire_details(db,now)
            clauses,params=['kind=?','report_id=?'],[kind,report_id]
            if job_id:
                clauses.append('job_id=?');params.append(job_id)
            if request_key:
                clauses.append('request_key=?');params.append(request_key)
            if ready_only:
                clauses.append("status='ready'")
            row=db.execute('SELECT * FROM detail_reports WHERE '+' AND '.join(clauses)+' ORDER BY started_at DESC,rowid DESC LIMIT 1',params).fetchone()
        return dict(row) if row else None

    def claim_detail(self, request_key, kind, report_id, context_digest, parent, context, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._expire_details(db,now)
            current=db.execute("SELECT body FROM manual_reports WHERE status='ready' ORDER BY started_at DESC LIMIT 1" if kind=='rolling' else "SELECT body FROM reports WHERE status='ready' ORDER BY report_date DESC LIMIT 1").fetchone()
            if current is None or json.loads(current['body'])!=parent:
                return 'stale',None
            old=db.execute('SELECT * FROM detail_reports WHERE kind=? AND report_id=? AND request_key=? ORDER BY started_at DESC,rowid DESC LIMIT 1',(kind,report_id,request_key)).fetchone()
            ttl=(8 if kind=='rolling' else 24)*3600000
            if old and (old['status']=='running' or (old['finished_at'] if old['status']=='ready' else old['started_at'])+ttl>now):
                return 'existing',old['job_id']
            for table in ('detail_reports','manual_reports','reports'):
                if db.execute("SELECT 1 FROM %s WHERE status='running' AND started_at>=? LIMIT 1" % table,(now-180000,)).fetchone():
                    return 'busy',None
            attempt=db.execute('SELECT COUNT(*) FROM detail_reports WHERE request_key=?',(request_key,)).fetchone()[0]+1
            job_id=hashlib.sha256((request_key+':'+str(attempt)).encode('utf-8')).hexdigest()
            db.execute("INSERT INTO detail_reports(job_id,report_id,kind,context_digest,request_key,status,started_at,period_start,period_end,parent_body,context_body) VALUES (?,?,?,?,?,'running',?,?,?,?,?)", (job_id,report_id,kind,context_digest,request_key,now,parent['periodStart'],parent['periodEnd'],json.dumps(parent,ensure_ascii=False,separators=(',',':')),json.dumps(context,ensure_ascii=False,separators=(',',':'))))
        return 'created',job_id

    def finish_detail(self, job_id, now, body=None, error_code=None):
        with self.connect() as db:
            self._expire_details(db,now)
            db.execute("UPDATE detail_reports SET status=?,finished_at=?,body=?,error_code=? WHERE job_id=? AND status='running'", ('error' if error_code else 'ready',now,json.dumps(body,ensure_ascii=False,separators=(',',':')) if body is not None else None,error_code,job_id))

    def finish_manual(self, snapshot_id, now, body=None, error_code=None):
        with self.connect() as db:
            if body and not error_code:
                self._save_evidence_topics(db, body, now)
            db.execute('UPDATE manual_reports SET status=?,finished_at=?,body=?,error_code=? WHERE snapshot_id=?',
                       ('error' if error_code else 'ready', now, json.dumps(body, ensure_ascii=False) if body else None, error_code, snapshot_id))

    @contextmanager
    def analysis_lock(self, blocking=True):
        # Bound model calls and full-history context memory across API/timer processes.
        descriptor = os.open(self.path+'.model.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise ValueError('Unsafe model lock')
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
