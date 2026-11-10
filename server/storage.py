import json
import os
import stat
import fcntl
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
