"""Explicit, versioned detailed interpretations of already generated brief reports."""
import hashlib
import json
import os
import re
import threading
from pathlib import Path

from .analysis import AnalysisError, enabled, relay_post
from .storage import now_ms

METHOD = 'cgm-detail-1'
MAX_BODY = 262144
KINDS = ('rolling', 'daily')
REPORT_ID = re.compile(r'^[0-9a-f]{64}$')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def identity(kind, report):
    return hashlib.sha256(canonical([kind, report]).encode('utf-8')).hexdigest()


def parent_report(store, kind):
    if kind == 'rolling':
        row = store.manual_report(ready_only=True)
        body = json.loads(row['body']) if row else None
    else:
        body = store.latest_ready_report()
    if (not isinstance(body, dict) or body.get('status') != 'ready' or
            type(body.get('periodStart')) is not int or type(body.get('periodEnd')) is not int or
            not 0 < body['periodStart'] < body['periodEnd'] or
            type(body.get('generatedAt')) is not int or body['generatedAt'] <= 0):
        return None
    return body


def attach_report_id(store, kind, view):
    parent = parent_report(store, kind)
    if parent and view.get('generatedAt') == parent['generatedAt'] and view.get('periodEnd') == parent['periodEnd']:
        return dict(view, reportId=identity(kind, parent))
    return view


def validate_target(payload):
    if not isinstance(payload, dict) or set(payload) != {'kind', 'reportId'}:
        raise ValueError('invalid_detail_target')
    kind, report_id = payload.get('kind'), payload.get('reportId')
    if kind not in KINDS or not isinstance(report_id, str) or not REPORT_ID.fullmatch(report_id):
        raise ValueError('invalid_detail_target')
    return kind, report_id


def build_context(store, parent, now):
    from .detail_context import build_context as build
    with store.analysis_lock(blocking=False):
        return build(store, parent, now)


def source_catalog():
    from .detail_sources import SOURCES
    return SOURCES


def prompt_text():
    return (Path(__file__).parent / 'detail_prompt.md').read_text(encoding='utf-8')


def _request_identity(report_id, context):
    digest = hashlib.sha256(canonical(context).encode('utf-8')).hexdigest()
    configuration = [METHOD, report_id, digest, os.environ.get('OPENAI_MODEL', 'gpt-6.1-terra'),
                     hashlib.sha256(prompt_text().encode('utf-8')).hexdigest()]
    return hashlib.sha256(canonical(configuration).encode('utf-8')).hexdigest(), digest


def _short_text(limit):
    return {'type': 'string', 'minLength': 1, 'maxLength': limit}


def response_request(context, parent, kind):
    ids = [item['id'] for item in source_catalog()]
    refs = {'type': 'array', 'maxItems': 8, 'items': {'type': 'string', 'enum': ids}}
    section = {'type': 'object', 'additionalProperties': False,
               'properties': {'title': _short_text(80), 'text': _short_text(3500), 'sourceIds': refs},
               'required': ['title', 'text', 'sourceIds']}
    hypothesis = {'type': 'object', 'additionalProperties': False,
                  'properties': {'title': _short_text(80), 'support': _short_text(1000),
                                 'against': _short_text(1000), 'verification': _short_text(1000),
                                 'confidence': {'type': 'string', 'enum': ['strong', 'moderate', 'weak']},
                                 'sourceIds': dict(refs, minItems=1)},
                  'required': ['title', 'support', 'against', 'verification', 'confidence', 'sourceIds']}
    action = {'type': 'object', 'additionalProperties': False,
              'properties': {'title': _short_text(80), 'text': _short_text(1200)}, 'required': ['title', 'text']}
    schema = {'type': 'object', 'additionalProperties': False,
              'properties': {'title': _short_text(80), 'summary': _short_text(500),
                             'sections': {'type': 'array', 'minItems': 3, 'maxItems': 6, 'items': section},
                             'hypotheses': {'type': 'array', 'maxItems': 3, 'items': hypothesis},
                             'actions': {'type': 'array', 'minItems': 1, 'maxItems': 5, 'items': action},
                             'limitations': {'type': 'array', 'maxItems': 3, 'items': _short_text(300)}},
              'required': ['title', 'summary', 'sections', 'hypotheses', 'actions', 'limitations']}
    request = {'model': os.environ.get('OPENAI_MODEL', 'gpt-6.1-terra'), 'store': False, 'stream': False, 'background': False,
               'reasoning': {'effort': 'medium'}, 'max_output_tokens': 10000,
               'input': [{'role': 'system', 'content': [{'type': 'input_text', 'text': prompt_text()}]},
                         {'role': 'user', 'content': [{'type': 'input_text', 'text': canonical({'kind': kind, 'briefReport': parent, 'observations': context})}]}],
               'text': {'format': {'type': 'json_schema', 'name': 'glucose_detailed_interpretation', 'strict': True, 'schema': schema}}}
    if len(canonical(request).encode('utf-8')) > MAX_BODY:
        raise AnalysisError('detail_input_limit')
    return request


def parse_response(response):
    if not isinstance(response, dict) or response.get('status') != 'completed':
        raise AnalysisError('detail_incomplete')
    chunks = []
    for item in response.get('output', []):
        if isinstance(item, dict) and item.get('type') == 'message':
            for part in item.get('content', []):
                if isinstance(part, dict) and part.get('type') == 'output_text':
                    chunks.append(part.get('text', ''))
    try:
        body = json.loads(''.join(chunks))
    except (TypeError, ValueError):
        raise AnalysisError('detail_invalid_json') from None
    if not isinstance(body, dict) or set(body) != {'title', 'summary', 'sections', 'hypotheses', 'actions', 'limitations'}:
        raise AnalysisError('detail_invalid_schema')
    def text(value, limit):
        return isinstance(value, str) and 1 <= len(value) <= limit and not any(ord(c) < 32 and c not in '\n\t\r' for c in value)
    if not text(body['title'], 80) or not text(body['summary'], 500):
        raise AnalysisError('detail_invalid_text')
    catalog = {item['id']: item for item in source_catalog()}
    def references(value, required=False):
        return (isinstance(value, list) and (1 if required else 0) <= len(value) <= 8 and
                all(isinstance(v, str) and v in catalog for v in value) and len(value) == len(set(value)))
    sections = body['sections']
    if not isinstance(sections, list) or not 3 <= len(sections) <= 6:
        raise AnalysisError('detail_invalid_sections')
    for item in sections:
        if (not isinstance(item, dict) or set(item) != {'title', 'text', 'sourceIds'} or
                not text(item['title'], 80) or not text(item['text'], 3500) or not references(item['sourceIds'])):
            raise AnalysisError('detail_invalid_sections')
    hypotheses = body['hypotheses']
    if not isinstance(hypotheses, list) or len(hypotheses) > 3:
        raise AnalysisError('detail_invalid_hypotheses')
    for item in hypotheses:
        if (not isinstance(item, dict) or set(item) != {'title', 'support', 'against', 'verification', 'confidence', 'sourceIds'} or
                not text(item['title'], 80) or any(not text(item[k], 1000) for k in ('support', 'against', 'verification')) or
                item['confidence'] not in ('strong', 'moderate', 'weak') or not references(item['sourceIds'], True)):
            raise AnalysisError('detail_invalid_hypotheses')
    actions = body['actions']
    if not isinstance(actions, list) or not 1 <= len(actions) <= 5:
        raise AnalysisError('detail_invalid_actions')
    for item in actions:
        if not isinstance(item, dict) or set(item) != {'title', 'text'} or not text(item['title'], 80) or not text(item['text'], 1200):
            raise AnalysisError('detail_invalid_actions')
    if not isinstance(body['limitations'], list) or len(body['limitations']) > 3 or any(not text(x, 300) for x in body['limitations']):
        raise AnalysisError('detail_invalid_limitations')
    used = {ref for item in sections + hypotheses for ref in item['sourceIds']}
    body['sources'] = [{k: item[k] for k in ('id', 'title', 'url')} for item in source_catalog() if item['id'] in used]
    if len(canonical(body).encode('utf-8')) > MAX_BODY:
        raise AnalysisError('detail_output_limit')
    return body


def _expires(kind, row):
    if not row:
        return None
    return (row['finished_at'] if row['status']=='ready' else row['started_at'])+(8 if kind=='rolling' else 24)*3600000


def _state(kind, report_id, parent=None, row=None, eligible=False, reason='', stale=False, saved=None):
    ready=row if row and row['status']=='ready' else saved
    stale=stale or bool(ready and row and ready['request_key']!=row['request_key'])
    return {'schemaVersion': 1, 'kind': kind, 'reportId': report_id,
            'status': row['status'] if row else ('available' if parent else 'unavailable'),
            'eligible': bool(eligible), 'reason': reason,
            'periodStart': row['period_start'] if row else parent['periodStart'] if parent else None,
            'periodEnd': row['period_end'] if row else parent['periodEnd'] if parent else None,
            'startedAt': row['started_at'] if row else None,
            'generatedAt': ready['finished_at'] if ready else None,
            'expiresAt': _expires(kind,row),
            'dataStale': bool(stale), 'report': json.loads(ready['body']) if ready and ready['body'] else None}


def detail_view(store, kind, report_id, now=None):
    now = now if now is not None else now_ms()
    validate_target({'kind': kind, 'reportId': report_id})
    row = store.detail_report(kind, report_id, now)
    saved = store.detail_report(kind,report_id,now,ready_only=True)
    parent = parent_report(store, kind)
    current = parent is not None and identity(kind, parent) == report_id
    if row and row['status'] == 'running':
        return _state(kind, report_id, parent, row, reason='详细解读正在生成，可继续正常使用。', stale=not current, saved=saved)
    if not current:
        return _state(kind, report_id, None, row, reason='简洁报告已更新，请返回后选择新报告；已生成的旧解读仍可查看。', stale=True, saved=saved)
    try:
        context = build_context(store, dict(parent,kind=kind), now)
    except BlockingIOError:
        return _state(kind,report_id,parent,row,reason='其他报告或资料正在处理中，请稍后再试。',saved=saved)
    request_key, digest = _request_identity(report_id, context)
    stale = bool(row and row['request_key'] != request_key)
    same = store.detail_report(kind, report_id, now, request_key=request_key)
    if same:
        row = same
        stale = False
    busy = store.analysis_busy(now)
    expired = bool(row and now>=_expires(kind,row))
    eligible = enabled() and not busy and (not row or stale or expired)
    reason = ('模型分析尚未启用。' if not enabled() else '其他报告正在生成，请稍后再试。' if busy else
              '该时段资料或解读方法有更新，可主动生成新版详细解读。' if stale else
              '已超过本类解读的复用时限，可主动生成新版详细解读。' if expired else
              '上次详细解读未确认完成，不自动重复调用。' if row and row['status']=='error' else
              '详细解读已生成，再次打开直接查看，不重复调用。' if row else '点击后生成这份报告对应时段的详细解读。')
    return _state(kind, report_id, parent, row, eligible, reason, stale, saved)


def request_detail(store, payload, now=None, launch=None, invoke=None):
    now = now if now is not None else now_ms()
    kind, report_id = validate_target(payload)
    parent = parent_report(store, kind)
    if parent is None or identity(kind, parent) != report_id:
        return 409, detail_view(store, kind, report_id, now)
    if not enabled():
        return 409, _state(kind, report_id, parent, reason='模型分析尚未启用。')
    row=store.detail_report(kind,report_id,now)
    saved=store.detail_report(kind,report_id,now,ready_only=True)
    try:
        context = build_context(store, dict(parent,kind=kind), now)
    except BlockingIOError:
        return 409,_state(kind,report_id,parent,row,reason='其他报告或资料正在处理中，请稍后再试。',saved=saved)
    request = response_request(context, parent, kind)
    request_key, digest = _request_identity(report_id, context)
    same = store.detail_report(kind, report_id, now, request_key=request_key)
    if same and now<_expires(kind,same):
        reason = {'ready': '详细解读已生成，直接查看。', 'running': '详细解读正在生成，无需重复提交。', 'error': '该次解读未确认完成，不重复调用。'}[same['status']]
        return (409 if same['status'] == 'error' else 200), _state(kind, report_id, parent, same, reason=reason,saved=saved)
    claimed,job_id = store.claim_detail(request_key, kind, report_id, digest, parent, context, now)
    if claimed == 'stale':
        return 409, detail_view(store,kind,report_id,now)
    if claimed == 'busy':
        row=store.detail_report(kind,report_id,now)
        return 409, _state(kind, report_id, parent,row,reason='其他报告正在生成，请稍后再试。',stale=bool(row and row['request_key']!=request_key),saved=saved)
    if claimed == 'existing':
        row = store.detail_report(kind, report_id, now, job_id)
        return (409 if row['status'] == 'error' else 200), _state(kind, report_id, parent, row, reason='已提交该次解读，请查看现有状态。',saved=saved)
    def run():
        try:
            with store.analysis_lock():
                result = parse_response((invoke or relay_post)(request, 'detail:' + job_id))
            store.finish_detail(job_id, now_ms(), body=result)
        except Exception as error:
            code = str(error) if isinstance(error, AnalysisError) else 'detail_internal_error'
            store.finish_detail(job_id, now_ms(), error_code=code)
    try:
        if launch is None:
            threading.Thread(target=run, name='ottai-detail-analysis', daemon=True).start()
        else:
            launch(run)
    except Exception:
        store.finish_detail(job_id, now_ms(), error_code='detail_launch_failed')
        return 503, detail_view(store, kind, report_id, now_ms())
    row = store.detail_report(kind, report_id, now)
    return 202, _state(kind, report_id, parent, row, reason='正在生成详细解读，可继续正常使用。',saved=saved)
