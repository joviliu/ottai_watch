import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

from .statistics import DAY, analysis_input
from .storage import now_ms

SOURCES = [
    {'title': 'International Consensus on Time in Range (2019)',
     'url': 'https://doi.org/10.2337/dci19-0028'},
    {'title': 'International Consensus on Use of Continuous Glucose Monitoring (2017)',
     'url': 'https://doi.org/10.2337/dc17-1600'},
    {'title': 'ADA Standards of Care: Diagnosis and Classification (2026)',
     'url': 'https://doi.org/10.2337/dc26-S002'},
    {'title': 'Shah et al. CGM Profiles in Healthy Nondiabetic Participants (2019)',
     'url': 'https://pubmed.ncbi.nlm.nih.gov/31127824/'},
]


class AnalysisError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def enabled():
    return os.environ.get('ANALYSIS_ENABLED', '').lower() == 'true'


def waiting_analysis(span, is_enabled, now=None):
    now = now if now is not None else now_ms()
    reason = '正在积累数据：超过72小时后开始每日观察分析。'
    if not is_enabled:
        reason = '每日模型分析尚未启用；血糖同步和统计可正常使用。'
    elif span['lastAt'] is not None and span['lastAt'] <= now-DAY:
        reason = '最近24小时没有新读数，暂停生成日报；恢复新数据后再作分析。'
    return {'status': 'waiting', 'generatedAt': None, 'reportDate': None, 'summary': reason,
            'sections': [], 'limitations': ['尚无每日模型报告。'], 'sources': SOURCES,
            'dataSpanHours': round((span['lastAt']-span['firstAt'])/3600000, 1) if span['firstAt'] is not None else 0}


def report_view(store, now=None):
    now = now if now is not None else now_ms()
    last = store.report()
    ready = store.latest_ready_report()
    span = store.span()
    stale = span['lastAt'] is not None and span['lastAt'] <= now-DAY
    if last and last['status'] == 'ready':
        if stale:
            ready['dataStale'] = True
            ready['limitations'] = list(ready['limitations']) + ['最近24小时没有新读数；当前保留的是历史日报，并非当前血糖评估。']
        return ready
    base = ready or waiting_analysis(span, enabled(), now)
    if last:
        base = dict(base)
        if last['status'] == 'error':
            base['status'] = 'error'
            base['latestAttemptDate'] = last['report_date']
            base['limitations'] = list(base['limitations']) + ['最近一次日报生成失败；保留之前报告，不自动重发模型请求。']
        elif last['status'] == 'running':
            base['limitations'] = list(base['limitations']) + ['今日日报请求处理中；服务重启后不自动重发不确定请求。']
    return base


def response_request(data, report_date, model):
    prompt = (Path(__file__).parent / 'daily_prompt.md').read_text(encoding='utf-8')
    schema = {'type': 'object', 'additionalProperties': False,
              'properties': {
                  'summary': {'type': 'string'},
                  'sections': {'type': 'array', 'items': {
                      'type': 'object', 'additionalProperties': False,
                      'properties': {'title': {'type': 'string'}, 'text': {'type': 'string'}},
                      'required': ['title', 'text']}},
                  'limitations': {'type': 'array', 'items': {'type': 'string'}}},
              'required': ['summary', 'sections', 'limitations']}
    return {'model': model, 'store': False, 'stream': False, 'background': False,
            'max_output_tokens': 3200,
            'input': [
                {'role': 'system', 'content': [{'type': 'input_text', 'text': prompt}]},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': json.dumps(
                    {'reportDate': report_date, 'observations': data}, ensure_ascii=False, separators=(',', ':'))}]}],
            'text': {'format': {'type': 'json_schema', 'name': 'glucose_daily_observation', 'strict': True, 'schema': schema}}}


def relay_post(payload, report_date):
    base = os.environ.get('OPENAI_RELAY_URL', '').rstrip('/')
    service_id = os.environ.get('OPENAI_RELAY_SERVICE_ID', '')
    secret = os.environ.get('OPENAI_RELAY_CLIENT_SECRET', '')
    if not base or not service_id or len(secret) < 32:
        raise AnalysisError('relay_not_configured')
    endpoint = base if base.endswith('/v1/responses') else base + '/v1/responses'
    parsed = urlparse(endpoint)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1', 'localhost') or parsed.query or parsed.fragment or parsed.username:
        raise AnalysisError('relay_must_be_loopback')
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    timestamp, nonce = str(now_ms()), secrets.token_hex(16)
    request_id = hashlib.sha256(('ottai-daily:' + service_id + ':' + report_date).encode()).hexdigest()
    fields = ['POST', parsed.path, service_id, 'application/json', timestamp, nonce, request_id,
              hashlib.sha256(body).hexdigest()]
    signature = hmac.new(secret.encode(), '\n'.join(fields).encode(), hashlib.sha256).hexdigest()
    headers = {'Content-Type': 'application/json', 'X-Relay-Service': service_id,
               'X-Relay-Timestamp': timestamp, 'X-Relay-Nonce': nonce,
               'X-Relay-Request-Id': request_id, 'X-Relay-Signature': signature}
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(Request(endpoint, data=body, headers=headers, method='POST'), timeout=115) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise AnalysisError('upstream_body_limit')
        return json.loads(raw.decode('utf-8'))
    except HTTPError as error:
        raise AnalysisError('relay_http_' + str(error.code)) from None
    except (URLError, TimeoutError, OSError):
        raise AnalysisError('relay_network_error') from None
    except (UnicodeError, ValueError):
        raise AnalysisError('relay_invalid_json') from None


def parse_response(response):
    if not isinstance(response, dict) or response.get('status') != 'completed':
        raise AnalysisError('model_incomplete')
    chunks = []
    for item in response.get('output', []):
        if isinstance(item, dict) and item.get('type') == 'message':
            for part in item.get('content', []):
                if isinstance(part, dict) and part.get('type') == 'output_text':
                    chunks.append(part.get('text', ''))
    try:
        result = json.loads(''.join(chunks))
    except (TypeError, ValueError):
        raise AnalysisError('model_invalid_json') from None
    if not isinstance(result, dict) or set(result) != {'summary', 'sections', 'limitations'}:
        raise AnalysisError('model_invalid_schema')
    if not isinstance(result['summary'], str) or not 1 <= len(result['summary']) <= 3000:
        raise AnalysisError('model_invalid_summary')
    sections, limitations = result['sections'], result['limitations']
    if not isinstance(sections, list) or not 1 <= len(sections) <= 12:
        raise AnalysisError('model_invalid_sections')
    if any(not isinstance(item, dict) or set(item) != {'title', 'text'} or
           not isinstance(item['title'], str) or not 1 <= len(item['title']) <= 100 or
           not isinstance(item['text'], str) or not 1 <= len(item['text']) <= 5000 for item in sections):
        raise AnalysisError('model_invalid_section')
    if not isinstance(limitations, list) or len(limitations) > 15 or any(not isinstance(item, str) or len(item) > 1000 for item in limitations):
        raise AnalysisError('model_invalid_limitations')
    return result


def generate_daily(store, now=None, invoke=None):
    now = now if now is not None else now_ms()
    span = store.span()
    if not enabled():
        return {'status': 'disabled'}
    if span['firstAt'] is None or span['lastAt'] - span['firstAt'] <= 3 * DAY:
        return {'status': 'insufficient_history'}
    if not any(item['sourceAt'] > now-DAY for item in store.readings(now-DAY, now)):
        return {'status': 'no_recent_data'}
    report_date = datetime.fromtimestamp(now / 1000, timezone(timedelta(hours=8))).date().isoformat()
    if not store.claim_report(report_date, now):
        return {'status': 'already_attempted', 'reportDate': report_date}
    try:
        readings = store.readings(now-365*DAY-300000, now)
        data = analysis_input(readings, now)
        request = response_request(data, report_date, os.environ.get('OPENAI_MODEL', 'gpt-6.1-terra'))
        response = (invoke or relay_post)(request, report_date)
        result = parse_response(response)
        limits = list(result['limitations'])
        limits += data['windows']['latest24h']['limitations']
        if span['lastAt'] - span['firstAt'] < 14 * DAY:
            limits.append('累计观察不足14天；当前为初步观察，不代表稳定长期模式。')
        result.update({'status': 'ready', 'generatedAt': now_ms(), 'reportDate': report_date,
                       'periodStart': now-DAY, 'periodEnd': now, 'limitations': list(dict.fromkeys(limits)),
                       'sources': SOURCES, 'methodVersion': 'cgm-observation-1'})
        store.finish_report(report_date, now_ms(), body=result)
        return {'status': 'ready', 'reportDate': report_date}
    except AnalysisError as error:
        store.finish_report(report_date, now_ms(), error_code=str(error))
        return {'status': 'error', 'reportDate': report_date, 'errorCode': str(error)}
    except Exception:
        store.finish_report(report_date, now_ms(), error_code='analysis_internal_error')
        return {'status': 'error', 'reportDate': report_date, 'errorCode': 'analysis_internal_error'}
