"""Run with python3 -m server.app (serve | run-daily). Python 3.6+ stdlib."""
import argparse
import hmac
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from .analysis import generate_daily, report_view, manual_status, request_manual, manual_report_view
from .statistics import DAY, NOMINAL_INTERVAL, historical_profile, metrics
from .storage import Store, now_ms, validate_batch
from .activity import MAX_ACTIVITY_BODY, dashboard_activity, validate_activity

MAX_BODY = 262144


def dashboard(store, now=None):
    now = now if now is not None else now_ms()
    points = store.readings(now-29*DAY-NOMINAL_INTERVAL, now+90000)
    daily, rolling = report_view(store, now), manual_report_view(store)
    available = [r for r in (daily, rolling) if r.get('generatedAt')]
    current = max(available, key=lambda r: r['generatedAt']) if available else daily
    return {'schemaVersion': 1, 'serverAt': now, 'latest': store.latest(),
            'readings': [r for r in points if now-DAY <= r['sourceAt'] <= now],
            'metrics': metrics(points, now-DAY, now),
            'comparison': historical_profile(points, now-29*DAY, now-DAY),
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

        def authorized(self, write=False):
            auth = self.headers.get('Authorization', '')
            if not auth.startswith('Bearer '):
                return False
            candidate = auth[7:]
            return hmac.compare_digest(candidate.encode('utf-8'), ingest_token.encode('utf-8')) or (
                not write and hmac.compare_digest(candidate.encode('utf-8'), read_token.encode('utf-8')))

        def do_GET(self):
            if self.path == '/health':
                return self.send_json(200, {'ok': True, 'schemaVersion': 1})
            if self.path != '/api/v1/dashboard':
                return self.send_json(404, {'error': 'not_found'})
            if not self.authorized():
                return self.send_json(401, {'error': 'unauthorized'})
            try:
                return self.send_json(200, dashboard(store))
            except Exception:
                return self.send_json(503, {'error': 'temporarily_unavailable'})

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
            if self.path not in ('/api/v1/readings', '/api/v1/activity'):
                return self.send_json(404, {'error': 'not_found'})
            if not self.authorized(write=True):
                return self.send_json(401, {'error': 'unauthorized'})
            if self.headers.get('Transfer-Encoding'):
                return self.send_json(400, {'error': 'unsupported_transfer_encoding'})
            length = self.headers.get('Content-Length', '')
            if not re.fullmatch(r'[0-9]{1,7}', length):
                return self.send_json(411, {'error': 'content_length_required'})
            length = int(length)
            if not 0 < length <= (MAX_ACTIVITY_BODY if self.path == '/api/v1/activity' else MAX_BODY):
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
                if self.path == '/api/v1/activity':
                    items = validate_activity(payload, now)
                    counts = store.ingest_activity(items, now)
                else:
                    items = validate_batch(payload, now)
                    counts = store.ingest(items, now)
                return self.send_json(200, {'ok': True, 'serverAt': now, **counts})
            except (ValueError, UnicodeError) as error:
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
