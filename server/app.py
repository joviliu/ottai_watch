"""Run with python3 -m server.app (serve | run-daily). Python 3.6+ stdlib."""
import argparse
import hmac
import json
import logging
import os
import re
import sys
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from .analysis import generate_daily, report_view, manual_status, request_manual, manual_report_view
from .statistics import DAY, NOMINAL_INTERVAL, historical_profile, metrics
from .storage import Store, now_ms, validate_batch
from .activity import MAX_ACTIVITY_BODY, ActivityValidationError, dashboard_activity, validate_activity
from .lifestyle import validate_event, identifier
from .meals import MAX_FOOD_BODY, request_recognition, job_view

MAX_BODY = 262144


def dashboard(store, now=None):
    now = now if now is not None else now_ms()
    points = store.readings(now-29*DAY-NOMINAL_INTERVAL, now+90000)
    daily, rolling = report_view(store, now), manual_report_view(store)
    markers = store.events(now-DAY,now+300000,101)
    available = [r for r in (daily, rolling) if r.get('generatedAt')]
    current = max(available, key=lambda r: r['generatedAt']) if available else daily
    return {'schemaVersion': 1, 'serverAt': now, 'latest': store.latest(),
            'readings': [r for r in points if now-DAY <= r['sourceAt'] <= now],
            'metrics': metrics(points, now-DAY, now),
            'comparison': historical_profile(points, now-29*DAY, now-DAY),
            'events':markers[-100:],'eventsTruncated':len(markers)>100,
            'activity': dashboard_activity(store.activity_snapshot(now-DAY,now), now-DAY,now,now),
            'analysis': current, 'dailyAnalysis': daily, 'rollingAnalysis': rolling, 'manualAnalysis': manual_status(store, now)}


def make_handler(store, ingest_token, read_token, analysis_token=""):
    if analysis_token and (len(analysis_token) < 32 or analysis_token in (ingest_token, read_token)):
        raise ValueError('Analysis capability must use a separate token of at least 32 characters')
    class Handler(BaseHTTPRequestHandler):
        server_version = 'Ottai/1'

        def log_message(self, format, *args):
            # Access paths, credentials, glucose values and model bodies stay out of logs.
            pass

        def send_json(self, status, body):
            raw = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self, write=False, allow_analysis=False):
            auth = self.headers.get('Authorization', '')
            if not auth.startswith('Bearer '):
                return False
            candidate = auth[7:]
            return hmac.compare_digest(candidate.encode('utf-8'), ingest_token.encode('utf-8')) or (
                not write and hmac.compare_digest(candidate.encode('utf-8'), read_token.encode('utf-8'))) or (allow_analysis and bool(analysis_token) and hmac.compare_digest(candidate.encode('utf-8'),analysis_token.encode('utf-8')))

        def do_GET(self):
            if self.path == '/health':
                return self.send_json(200, {'ok':True,'schemaVersion':1})
            parsed=urlsplit(self.path)
            if parsed.path not in ('/api/v1/dashboard','/api/v1/events','/api/v1/meals/recognize') or parsed.fragment:
                return self.send_json(404, {'error':'not_found'})
            photo=parsed.path=='/api/v1/meals/recognize'
            if not self.authorized(write=photo,allow_analysis=parsed.path!='/api/v1/dashboard'):
                return self.send_json(401, {'error':'unauthorized'})
            try:
                if parsed.path=='/api/v1/dashboard':
                    if parsed.query:
                        raise ValueError('invalid_query')
                    return self.send_json(200,dashboard(store))
                query=parse_qs(parsed.query,keep_blank_values=True)
                if any(len(v)!=1 for v in query.values()):
                    raise ValueError('invalid_query')
                if photo:
                    if set(query)!={'requestId'}:
                        raise ValueError('invalid_query')
                    result=job_view(store,identifier(query['requestId'][0]))
                    return self.send_json(200 if result else 404,result or {'error':'not_found'})
                if set(query)-{'startAt','endAt'}:
                    raise ValueError('invalid_query')
                now=now_ms()
                start=int(query.get('startAt',[str(now-DAY)])[0]);end=int(query.get('endAt',[str(now)])[0])
                if not 0<start<=end<=now+300000 or start<now-365*DAY or end-start>365*DAY:
                    raise ValueError('invalid_query')
                rows=store.events(start,end,1001)
                return self.send_json(200,{'events':rows[-1000:],'eventsTruncated':len(rows)>1000})
            except (ValueError,TypeError):
                return self.send_json(400,{'error':'invalid_query'})
            except Exception:
                return self.send_json(503,{'error':'temporarily_unavailable'})

        def do_POST(self):
            if self.path == '/api/v1/analysis':
                candidate = self.headers.get('Authorization', '')
                allowed = [ingest_token] + ([analysis_token] if analysis_token else [])
                if not any(hmac.compare_digest(candidate.encode(), ('Bearer '+token).encode()) for token in allowed):
                    return self.send_json(401, {'error': 'unauthorized'})
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Length', '0') != '0':
                    return self.send_json(400, {'error': 'empty_body_required'})
                try:
                    status, result = request_manual(store)
                    return self.send_json(status, result)
                except Exception:
                    return self.send_json(503, {'error': 'temporarily_unavailable'})
            if self.path not in ('/api/v1/readings','/api/v1/activity','/api/v1/events','/api/v1/events/delete','/api/v1/meals/recognize'):
                return self.send_json(404, {'error': 'not_found'})
            if not self.authorized(write=True,allow_analysis=self.path in ('/api/v1/events','/api/v1/events/delete','/api/v1/meals/recognize')):
                return self.send_json(401, {'error': 'unauthorized'})
            if self.headers.get('Transfer-Encoding'):
                return self.send_json(400, {'error': 'unsupported_transfer_encoding'})
            length = self.headers.get('Content-Length', '')
            if not re.fullmatch(r'[0-9]{1,7}', length):
                return self.send_json(411, {'error': 'content_length_required'})
            length = int(length)
            if not 0 < length <= (MAX_ACTIVITY_BODY if self.path=='/api/v1/activity' else MAX_FOOD_BODY if self.path=='/api/v1/meals/recognize' else MAX_BODY):
                return self.send_json(413, {'error': 'body_limit'})
            if self.headers.get_content_type() != 'application/json':
                return self.send_json(415, {'error': 'json_required'})
            try:
                self.connection.settimeout(15)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('Incomplete body')
                now = now_ms()
                payload = json.loads(raw.decode('utf-8'))
                if self.path == '/api/v1/events':
                    event,expected=validate_event(payload,now)
                    return self.send_json(200,{'ok':True,'event':store.upsert_event(event,expected,now)})
                if self.path == '/api/v1/events/delete':
                    if not isinstance(payload,dict) or set(payload)-{'id','expectedUpdatedAt'}:
                        raise ValueError('invalid_event')
                    expected=payload.get('expectedUpdatedAt')
                    if expected is not None and (type(expected) is not int or expected<=0):
                        raise ValueError('invalid_event')
                    store.delete_event(identifier(payload.get('id')),expected,now)
                    return self.send_json(200,{'ok':True})
                if self.path == '/api/v1/meals/recognize':
                    status,result=request_recognition(store,payload,now)
                    return self.send_json(status,result)
                if self.path == '/api/v1/activity':
                    items = validate_activity(payload, now)
                    counts = store.ingest_activity(items, now)
                else:
                    items = validate_batch(payload, now)
                    counts = store.ingest(items, now)
                return self.send_json(200, {'ok': True, 'serverAt': now, **counts})
            except ActivityValidationError as error:
                # Error text is constructor-whitelisted, never payload-derived data.
                logging.warning('activity_validation code=%s', str(error))
                return self.send_json(400, {'error': 'invalid_activity', 'reason': str(error)})
            except (ValueError, UnicodeError) as error:
                if str(error)=='event_conflict':
                    return self.send_json(409,{'error':'event_conflict','reason':'记录已在其他设备更新，请刷新后重试。'})
                if str(error)=='recognition_conflict':
                    return self.send_json(409,{'error':'recognition_conflict','reason':'识别编号已用于另一张照片。'})
                if str(error) in ('food_busy','food_daily_limit','event_limit'):
                    return self.send_json(429,{'error':str(error),'reason':{'food_busy':'上一张照片仍在识别，请稍后查看。','food_daily_limit':'今日主动照片识别已达30次。','event_limit':'该时段记录过多，请先整理。'}[str(error)]})
                if self.path in ('/api/v1/events','/api/v1/events/delete','/api/v1/meals/recognize'):
                    return self.send_json(400,{'error':'invalid_photo' if self.path=='/api/v1/meals/recognize' else 'invalid_event'})
                if str(error) == 'snapshot_conflict':
                    return self.send_json(409, {'error': 'snapshot_conflict'})
                return self.send_json(400, {'error': 'invalid_activity' if self.path=='/api/v1/activity' else 'invalid_readings'})
            except Exception:
                return self.send_json(503, {'error': 'temporarily_unavailable'})
    return Handler


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['serve', 'run-daily'], nargs='?', default='serve')
    args = parser.parse_args()
    os.umask(0o077)
    store = Store(os.environ.get('DATABASE_PATH', '/var/lib/ottai-cloud/glucose.sqlite3'))
    if args.command == 'run-daily':
        result = generate_daily(store)
        print(json.dumps(result))  # Only status/date/error code, never data or credentials.
        return 1 if result['status'] == 'error' else 0
    ingest = os.environ.get('INGEST_TOKEN', '')
    reader = os.environ.get('READ_TOKEN', '')
    if len(ingest) < 32 or len(reader) < 32 or hmac.compare_digest(ingest, reader):
        raise SystemExit('Separate INGEST_TOKEN and READ_TOKEN of at least 32 characters are required')
    host = os.environ.get('BIND_HOST', '127.0.0.1')
    if host not in ('127.0.0.1', '::1'):
        raise SystemExit('Bind loopback only; expose HTTPS through the configured reverse proxy')
    httpd = ThreadedServer((host, int(os.environ.get('BIND_PORT', '18776'))), make_handler(store, ingest, reader, os.environ.get('ANALYZE_TOKEN', '')))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
