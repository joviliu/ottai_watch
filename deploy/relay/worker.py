"""SG-only worker for the existing provider-pull-v1 protocol over an SSH tunnel.

Only /v1/responses is accepted. OpenAI credentials never leave SG. An uncertain
provider request is not retried; daily reservations survive process restarts.
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import time
import urllib.error
import urllib.request

MAX_BODY = 256 * 1024
ORIGIN = 'http://127.0.0.1:18778'
PROVIDER = 'https://api.openai.com/v1/responses'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def bounded(response, limit=MAX_BODY):
    body = response.read(limit+1)
    if len(body) > limit:
        raise ValueError('body_limit')
    return body


class Worker:
    def __init__(self):
        self.secret = os.environ['AI_RELAY_SECRET'].encode()
        self.identity = os.environ.get('AI_WORKER_ID', 'sg-ottai')
        self.key = pathlib.Path(os.environ['OPENAI_API_KEY_FILE']).read_text().strip()
        if not self.key.startswith('sk-') or len(self.secret) < 32:
            raise ValueError('invalid_private_configuration')
        self.state = pathlib.Path(os.environ['AI_RELAY_STATE_DIR']) / 'worker.json'
        self.state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def reserve(self, request_id):
        day = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
        saved = json.loads(self.state.read_text()) if self.state.exists() else {}
        if saved.get('day') != day:
            saved = {'day': day, 'seen': []}
        if request_id in saved['seen'] or len(saved['seen']) >= 2:
            return False
        saved['seen'].append(request_id)
        tmp = self.state.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            os.chmod(str(tmp), 0o600)
            json.dump(saved, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(self.state))
        return True

    def relay(self, action, extra):
        body = json.dumps(dict(workerId=self.identity, action=action,
                               protocol='provider-pull-v1', **extra), separators=(',', ':')).encode()
        at, nonce = str(int(time.time()*1000)), secrets.token_hex(16)
        sig = hmac.new(self.secret, (at+'\n'+nonce+'\n'+hashlib.sha256(body).hexdigest()).encode(), hashlib.sha256).hexdigest()
        req = urllib.request.Request(ORIGIN+'/api/ai/worker/'+action, body, headers={
            'Content-Type': 'application/json', 'X-AI-Timestamp': at,
            'X-AI-Nonce': nonce, 'X-AI-Signature': sig})
        response = self.opener.open(req, timeout=25)
        return response.headers, bounded(response)

    def execute(self, headers, raw):
        names = ['Job', 'Lease', 'Request', 'Path', 'Type', 'Deadline']
        job, lease, request_id, path, content_type, deadline = [headers.get('X-AI-Provider-'+x, '') for x in names]
        if not re.fullmatch('[a-f0-9]{64}', job) or not re.fullmatch('[a-f0-9]{48}', lease) or not re.fullmatch('[a-f0-9]{64}', request_id):
            raise ValueError('invalid_job')
        result = {'jobId': job, 'leaseId': lease}
        try:
            if path != '/v1/responses' or content_type != 'application/json' or len(raw) > MAX_BODY:
                raise ValueError('invalid_job')
            remaining = int(deadline)/1000-time.time()
            payload = json.loads(raw)
            if remaining < 1 or payload.get('store') is not False or payload.get('stream') or payload.get('background'):
                raise ValueError('invalid_job')
            if not self.reserve(request_id):
                raise ValueError('already_reserved')
            req = urllib.request.Request(PROVIDER, raw, headers={
                'Content-Type': 'application/json', 'Authorization': 'Bearer '+self.key})
            try:
                response = self.opener.open(req, timeout=min(75, remaining))
            except urllib.error.HTTPError as error:
                response = error
            data = bounded(response)
            if response.code != 200 and not 400 <= response.code <= 599:
                raise ValueError('invalid_status')
            result.update(status=response.code, body=base64.b64encode(data).decode())
        except Exception:
            result['error'] = {'code': 'provider_uncertain'}
        self.relay('result', result)

    def run(self):
        while True:
            try:
                headers, raw = self.relay('poll', {'providerReady': True, 'capacity': 1})
                if headers.get('Content-Type') == 'application/octet-stream':
                    self.execute(headers, raw)
            except Exception:
                # Errors contain no payloads, credentials, or upstream error text.
                time.sleep(5)


if __name__ == '__main__':
    Worker().run()
