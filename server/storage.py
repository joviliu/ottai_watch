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
                    record_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    start_at INTEGER NOT NULL, end_at INTEGER NOT NULL,
                    modified_at INTEGER NOT NULL, body TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS activity_interval ON activity_records(start_at,end_at);
                CREATE TABLE IF NOT EXISTS activity_state (
                    source TEXT PRIMARY KEY, synced_at INTEGER NOT NULL, digest TEXT NOT NULL,
                    status TEXT NOT NULL, readable_kinds TEXT NOT NULL,
                    window_start INTEGER NOT NULL, window_end INTEGER NOT NULL,
                    last_success_at INTEGER, origin_app TEXT
                );
                CREATE TABLE IF NOT EXISTS activity_coverage (
                    kind TEXT NOT NULL, start_at INTEGER NOT NULL, end_at INTEGER NOT NULL,
                    PRIMARY KEY(kind,start_at)
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
            ''')
            columns = [r[1] for r in db.execute('PRAGMA table_info(activity_state)').fetchall()]
            if 'origin_app' not in columns:
                db.execute('ALTER TABLE activity_state ADD COLUMN origin_app TEXT')
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

        One collector/source. Older uploads never delete newer observations, and a
        changed source record never regresses to an older modifiedAt revision.
        """
        from .activity import canonical
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
                old_rows = db.execute('SELECT * FROM activity_records WHERE start_at>=? AND start_at<?',
                                      (snapshot['windowStart'], snapshot['windowEnd'])).fetchall()
                present = {row['id'] for row in snapshot['records']}
                for row in old_rows:
                    if row['kind'] in snapshot['readableKinds'] and row['record_id'] not in present and row['modified_at'] <= snapshot['syncedAt']:
                        db.execute('DELETE FROM activity_records WHERE record_id=?', (row['record_id'],))
                        counts['deleted'] += 1
                for record in snapshot['records']:
                    body = canonical(record)
                    old = db.execute('SELECT * FROM activity_records WHERE record_id=?', (record['id'],)).fetchone()
                    if old is None:
                        db.execute('INSERT INTO activity_records VALUES (?,?,?,?,?,?)',
                                   (record['id'], record['kind'], record['startAt'], record['endAt'], record['modifiedAt'], body))
                        counts['inserted'] += 1
                    elif record['modifiedAt'] < old['modified_at'] or old['body'] == body:
                        counts['unchanged'] += 1
                    else:
                        db.execute('UPDATE activity_records SET kind=?,start_at=?,end_at=?,modified_at=?,body=? WHERE record_id=?',
                                   (record['kind'], record['startAt'], record['endAt'], record['modifiedAt'], body, record['id']))
                        counts['updated'] += 1
                # Union the windows successfully read for each kind. This describes
                # query availability, never continuous wear or HR sample coverage.
                for kind in snapshot['readableKinds']:
                    a, b = snapshot['windowStart'], snapshot['windowEnd']
                    overlaps = db.execute('SELECT start_at,end_at FROM activity_coverage WHERE kind=? AND start_at<=? AND end_at>=?', (kind,b,a)).fetchall()
                    for prior in overlaps:
                        a, b = min(a,prior['start_at']), max(b,prior['end_at'])
                    db.execute('DELETE FROM activity_coverage WHERE kind=? AND start_at<=? AND end_at>=?', (kind,b,a))
                    db.execute('INSERT INTO activity_coverage VALUES (?,?,?)', (kind,a,b))
            last_success = snapshot['syncedAt'] if snapshot['status']=='available' else (state['last_success_at'] if state else None)
            db.execute('INSERT OR REPLACE INTO activity_state VALUES (?,?,?,?,?,?,?,?,?)',
                       (snapshot['source'],snapshot['syncedAt'],digest,snapshot['status'],canonical(snapshot['readableKinds']),
                        snapshot['windowStart'],snapshot['windowEnd'],last_success,canonical(snapshot.get('originApp'))))
        return dict(counts, status='accepted')

    def activity_snapshot(self, start, end):
        from .activity import SOURCE
        with self.connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT * FROM activity_state WHERE source=?', (SOURCE,)).fetchone()
            identity = self._activity_identity(db,start,end)
            records = [json.loads(r['body']) for r in db.execute(
                'SELECT body FROM activity_records WHERE start_at<? AND (end_at>? OR (start_at=end_at AND start_at>=?)) ORDER BY start_at,record_id', (end,start,start)).fetchall()]
            coverage = {kind: [] for kind in ('exercise','heart_rate','steps')}
            for r in db.execute('SELECT * FROM activity_coverage WHERE start_at<? AND end_at>? ORDER BY start_at', (end,start)).fetchall():
                coverage[r['kind']].append([max(start,r['start_at']),min(end,r['end_at'])])
        state = {'status': 'not_connected', 'readableKinds': [], 'lastSyncedAt': None}
        if row:
            state.update(status=row['status'],readableKinds=json.loads(row['readable_kinds']),lastSyncedAt=row['synced_at'],
                         lastSuccessfulSyncAt=row['last_success_at'],windowStart=row['window_start'],windowEnd=row['window_end'],
                         originApp=json.loads(row['origin_app']) if row['origin_app'] else None)
        result = {'state': state, 'records': records, 'coverage': coverage}
        result['digest'] = identity
        return result

    def _activity_identity(self, db, start, end):
        """Hash stored canonical bodies without materializing HR arrays for status polls."""
        from .activity import canonical, SOURCE
        state = db.execute('SELECT status,readable_kinds FROM activity_state WHERE source=?', (SOURCE,)).fetchone()
        digest = hashlib.sha256()
        digest.update(canonical([state['status'],json.loads(state['readable_kinds'])] if state else ['not_connected',[]]).encode())
        for r in db.execute('SELECT kind,start_at,end_at FROM activity_coverage WHERE start_at<? AND end_at>? ORDER BY kind,start_at', (end,start)):
            digest.update(canonical([r['kind'],max(start,r['start_at']),min(end,r['end_at'])]).encode())
        for r in db.execute('SELECT body FROM activity_records WHERE start_at<? AND (end_at>? OR (start_at=end_at AND start_at>=?)) ORDER BY start_at,record_id', (end,start,start)):
            digest.update(b'\0'); digest.update(r['body'].encode('utf-8'))
        return digest.hexdigest()

    def activity_identity(self, start, end):
        with self.connect() as db:
            db.execute('BEGIN')
            return self._activity_identity(db,start,end)

    def claim_report(self, day, now):
        """Unique day is also the network-call lock; failed calls are not auto-retried."""
        with self.connect() as db:
            result = db.execute('INSERT OR IGNORE INTO reports(report_date,status,started_at) VALUES (?,?,?)', (day, 'running', now))
            return result.rowcount == 1

    def finish_report(self, day, now, body=None, error_code=None):
        with self.connect() as db:
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
            latest = db.execute('SELECT MAX(started_at) FROM manual_reports').fetchone()[0]
            if latest is not None and now-latest < 30*60*1000:
                return 'cooldown'
            db.execute('INSERT INTO manual_reports(snapshot_id,window_end,status,started_at) VALUES (?,?,?,?)',
                       (snapshot_id, window_end, 'running', now))
            return 'created'

    def finish_manual(self, snapshot_id, now, body=None, error_code=None):
        with self.connect() as db:
            db.execute('UPDATE manual_reports SET status=?,finished_at=?,body=?,error_code=? WHERE snapshot_id=?',
                       ('error' if error_code else 'ready', now, json.dumps(body, ensure_ascii=False) if body else None, error_code, snapshot_id))

    @contextmanager
    def analysis_lock(self):
        # One SG worker: serialize scheduled and manual calls across API/timer processes.
        descriptor = os.open(self.path+'.model.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise ValueError('Unsafe model lock')
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
