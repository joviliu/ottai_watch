import hashlib
import hmac
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

from .statistics import DAY, analysis_input
from .excursions import candidate_excursions, day_quality
from .storage import now_ms
from .activity import analysis_context

SOURCES = [
    {'title': 'International Consensus on Time in Range (2019)',
     'url': 'https://doi.org/10.2337/dci19-0028'},
    {'title': 'International Consensus on Use of Continuous Glucose Monitoring (2017)',
     'url': 'https://doi.org/10.2337/dc17-1600'},
    {'title': 'ADA Standards of Care: Diagnosis and Classification (2026)',
     'url': 'https://doi.org/10.2337/dc26-S002'},
    {'title': 'Endotext: Assessing Insulin Sensitivity and Resistance in Humans',
     'url': 'https://www.ncbi.nlm.nih.gov/books/NBK278954/'},
    {'title': 'Kahn et al. The β Cell in Diabetes (Endocrine Reviews, 2021)',
     'url': 'https://doi.org/10.1210/endrev/bnab021'},
    {'title': 'Endotext: Glucagon Physiology',
     'url': 'https://www.ncbi.nlm.nih.gov/books/NBK279127/'},
    {'title': 'CGM-only meal detection in healthy adults (2026)',
     'url': 'https://doi.org/10.1038/s41598-026-50699-5'},
    {'title': 'ADA Physical Activity/Exercise Position Statement (2016)',
     'url': 'https://doi.org/10.2337/dc16-1728'},
    {'title': 'ACSM Exercise/Physical Activity Consensus Statement (2022)',
     'url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8802999/'},
    {'title': 'Broussard et al. Experimental Sleep Restriction and Insulin Signaling (2012)',
     'url': 'https://pubmed.ncbi.nlm.nih.gov/23070488/'},
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
    reason = '正在积累数据：超过72小时后开始自动日报；最近24小时资料就绪后可手动分析。'
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
    schema = {'type':'object','additionalProperties':False,'properties':{
        'summary':{'type':'string','maxLength':120},
        'highlights':{'type':'array','minItems':1,'maxItems':3,'items':{
            'type':'object','additionalProperties':False,'properties':{
                'title':{'type':'string','maxLength':24}, 'text':{'type':'string','maxLength':120},
                'severity':{'type':'string','enum':['info','watch','positive']},
                'action':{'type':'string','maxLength':60}},'required':['title','text','severity','action']}},
        'evidence':{'type':'array','maxItems':1,'items':{
            'type':'object','additionalProperties':False,'properties':{
                'topic':{'type':'string','enum':['healthy_reference','meal_recovery','meal_composition','postmeal_activity','sleep_context','measurement_artifacts','personal_baseline','physiology_limits']},
                'title':{'type':'string','maxLength':40},'text':{'type':'string','maxLength':160},
                'sourceUrl':{'type':'string','enum':[r['url'] for r in SOURCES]}},
            'required':['topic','title','text','sourceUrl']}},
        'limitations':{'type':'array','maxItems':2,'items':{'type':'string','maxLength':100}}},
        'required':['summary','highlights','evidence','limitations']}
    return {'model':model,'store':False,'stream':False,'background':False,
            'reasoning':{'effort':'low'},'max_output_tokens':2800,
            'input':[{'role':'system','content':[{'type':'input_text','text':prompt}]},
                     {'role':'user','content':[{'type':'input_text','text':json.dumps({'reportDate':report_date,'observations':data},ensure_ascii=False,separators=(',',':'))}]}],
            'text':{'format':{'type':'json_schema','name':'glucose_daily_observation','strict':True,'schema':schema}}}


def relay_post(payload, report_date, food=False):
    prefix = 'FOOD_OPENAI_RELAY_' if food else 'OPENAI_RELAY_'
    base = os.environ.get(prefix+'URL', '').rstrip('/')
    service_id = os.environ.get(prefix+'SERVICE_ID', '')
    secret = os.environ.get(prefix+'CLIENT_SECRET', '')
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
    if not isinstance(response,dict) or response.get('status')!='completed':
        raise AnalysisError('model_incomplete')
    chunks=[]
    for item in response.get('output',[]):
        if isinstance(item,dict) and item.get('type')=='message':
            for part in item.get('content',[]):
                if isinstance(part,dict) and part.get('type')=='output_text':
                    chunks.append(part.get('text',''))
    try:
        result=json.loads(''.join(chunks))
    except (TypeError,ValueError):
        raise AnalysisError('model_invalid_json') from None
    legacy={'summary','sections','limitations'}
    modern={'summary','highlights','evidence','limitations'}
    if not isinstance(result,dict) or set(result) not in (legacy,modern):
        raise AnalysisError('model_invalid_schema')
    is_modern=set(result)==modern
    if not isinstance(result['summary'],str) or not 1<=len(result['summary'])<=(120 if is_modern else 3000):
        raise AnalysisError('model_invalid_summary')
    limitations=result['limitations']
    if not isinstance(limitations,list) or len(limitations)>(2 if is_modern else 15) or any(not isinstance(x,str) or len(x)>(100 if is_modern else 1000) for x in limitations):
        raise AnalysisError('model_invalid_limitations')
    if is_modern:
        highlights=result['highlights'];evidence=result['evidence']
        if not isinstance(highlights,list) or not 1<=len(highlights)<=3:
            raise AnalysisError('model_invalid_highlights')
        for item in highlights:
            if not isinstance(item,dict) or set(item)!={'title','text','severity','action'} or item['severity'] not in ('info','watch','positive') or any(not isinstance(item[k],str) or not (0 if k=='action' else 1)<=len(item[k])<=limit for k,limit in (('title',24),('text',120),('action',60))):
                raise AnalysisError('model_invalid_highlights')
        topics={'healthy_reference','meal_recovery','meal_composition','postmeal_activity','sleep_context','measurement_artifacts','personal_baseline','physiology_limits'}
        if not isinstance(evidence,list) or len(evidence)>1:
            raise AnalysisError('model_invalid_evidence')
        for item in evidence:
            if not isinstance(item,dict) or set(item)!={'topic','title','text','sourceUrl'} or not isinstance(item['topic'],str) or item['topic'] not in topics or not isinstance(item['sourceUrl'],str) or item['sourceUrl'] not in {r['url'] for r in SOURCES} or any(not isinstance(item[k],str) or not 1<=len(item[k])<=limit for k,limit in (('title',40),('text',160))):
                raise AnalysisError('model_invalid_evidence')
        result['sections']=[{'title':item['title'],'text':item['text']+('\n'+item['action'] if item['action'] else '')} for item in highlights]
    else:
        sections=result['sections']
        if not isinstance(sections,list) or not 1<=len(sections)<=12 or any(not isinstance(item,dict) or set(item)!={'title','text'} or not isinstance(item['title'],str) or not 1<=len(item['title'])<=100 or not isinstance(item['text'],str) or not 1<=len(item['text'])<=5000 for item in sections):
            raise AnalysisError('model_invalid_section')
    return result


def _report_body(readings, end, trigger, date, now, invoke, request_identity, activity=None, events=None, explained_topics=None):
    data = analysis_input(readings, end)
    data['trigger'] = trigger
    data['periodMeaning'] = ('固定前一自然日00:00–24:00' if trigger == 'scheduled_daily' else '截至最新测量的滚动24小时')
    data['latest24hQuality'] = day_quality(readings, end)
    data['previous24hQuality'] = day_quality([r for r in readings if r['sourceAt'] <= end-DAY], end-DAY)
    data['candidateExcursions'] = candidate_excursions(readings, end-DAY, end)
    data['previous24hExcursions'] = candidate_excursions(readings, end-2*DAY, end-DAY)
    from .lifestyle import context as event_context
    data['lifestyle'] = {'latest24h':event_context(events or [],end-DAY,end),'previous24h':event_context(events or [],end-2*DAY,end-DAY)}
    data['recentlyExplainedTopics'] = explained_topics or []
    if activity is not None:
        data['activity'] = {
            'latest24h': analysis_context(activity, readings, end-DAY, end, now, data['candidateExcursions']),
            'previous24h': analysis_context(activity, readings, end-2*DAY, end-DAY, now, data['previous24hExcursions'])}
    request = response_request(data, date, os.environ.get('OPENAI_MODEL', 'gpt-6.1-terra'))
    if len(json.dumps(request,ensure_ascii=False,separators=(',',':')).encode('utf-8')) > 262144:
        raise AnalysisError('analysis_input_limit')
    result = parse_response((invoke or relay_post)(request, request_identity))
    if 'evidence' in result:
        result['evidence']=[e for e in result['evidence'] if e['topic'] not in (explained_topics or [])]
    referenced={e['sourceUrl'] for e in result.get('evidence',[])}
    result.update(status='ready',generatedAt=now_ms(),reportDate=date,
                  periodStart=end-DAY,periodEnd=end,sources=[s for s in SOURCES if s['url'] in referenced],
                  methodVersion='cgm-observation-5',trigger=trigger,activityContextIncluded=activity is not None,
                  lifestyleContextIncluded=bool(events))
    return result


def generate_daily(store, now=None, invoke=None):
    now = now if now is not None else now_ms()
    span = store.span()
    if not enabled():
        return {'status': 'disabled'}
    if span['firstAt'] is None or span['lastAt']-span['firstAt'] <= 3*DAY:
        return {'status': 'insufficient_history'}
    if not any(item['sourceAt'] > now-DAY for item in store.readings(now-DAY, now)):
        return {'status': 'no_recent_data'}
    tz = timezone(timedelta(hours=8))
    midnight = datetime.fromtimestamp(now/1000, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    end = int(midnight.timestamp()*1000)
    date = (midnight-timedelta(days=1)).date().isoformat()
    if not store.claim_report(date, now):
        return {'status': 'already_attempted', 'reportDate': date}
    try:
        rows = store.readings(end-365*DAY-300000, end)
        with store.analysis_lock():
            body = _report_body(rows, end, 'scheduled_daily', date, now, invoke, 'daily:'+date,
                                store.activity_snapshot(end-2*DAY,end,now),
                                store.events(end-2*DAY,end),store.recent_evidence_topics())
        store.finish_report(date, now_ms(), body=body)
        return {'status': 'ready', 'reportDate': date}
    except Exception as error:
        code = str(error) if isinstance(error, AnalysisError) else 'analysis_internal_error'
        store.finish_report(date, now_ms(), error_code=code)
        return {'status': 'error', 'reportDate': date, 'errorCode': code}


def _snapshot_id(points, end, activity_digest=None, event_digest=None):
    observed = [[r['sourceAt'],r['value'],r['trend']] for r in points if end-2*DAY-300000 <= r['sourceAt'] <= end]
    return hashlib.sha256(json.dumps(['manual-v5', end, observed, activity_digest, event_digest], separators=(',', ':')).encode()).hexdigest()


def manual_report_view(store):
    last = store.manual_report()
    ready = store.manual_report(ready_only=True)
    if ready:
        body = json.loads(ready['body'])
    else:
        body = {'status': 'waiting', 'summary': '最近24小时资料就绪后可手动分析。', 'sections': [], 'limitations': [], 'sources': SOURCES}
    if last and last['status'] != 'ready':
        body['status'] = last['status']
        body['limitations'] = list(body.get('limitations', [])) + (['手动分析生成中。'] if last['status']=='running' else ['最近一次手动分析失败；保留之前结果，不自动重发不确定请求。'])
    return body


def manual_status(store, now=None, points=None, activity=None, events=None):
    now = now if now is not None else now_ms()
    points = points if points is not None else store.readings(now-2*DAY-300000, now)
    end = points[-1]['sourceAt'] if points else now
    quality = day_quality(points, end)
    if now-end > 10*60000:
        quality.update(ready=False, latestFresh=False, reason=quality['reason']+' 请先恢复最新读数同步。')
    activity_digest = activity['digest'] if activity is not None else store.activity_identity(end-2*DAY,end,now)
    event_digest = events['digest'] if events is not None else store.event_identity(end-2*DAY,end)
    key = _snapshot_id(points, end, activity_digest, event_digest)
    same = store.manual_report(key)
    last = store.manual_report()
    cooldown = max(0, (last['started_at']+30*60000-now)//1000) if last else 0
    detail_busy = store.active_detail(now)
    status = 'available' if quality['ready'] else 'insufficient_data'
    reason = quality['reason']
    if not enabled():
        status, reason = 'disabled', '模型分析尚未启用。'
    elif same:
        status = same['status']
        reason = {'running':'该快照正在分析，无需重复提交。','ready':'该数据快照已有分析；有新数据且间隔满30分钟后可再次分析。',
                  'error':'该快照已尝试分析，结果不确定时不重复计费；新快照间隔满30分钟后可再试。'}.get(status, reason)
    elif last and last['status'] == 'running' and now-last['started_at'] < 180000:
        status, reason = 'running', '上一份动态分析仍在生成，无需重复提交。'
    elif cooldown:
        status, reason = 'cooldown', '距离上次手动分析不足30分钟，约%d分钟后可再次分析。' % ((cooldown+59)//60)
    elif detail_busy:
        status, reason = 'busy', '详细解读正在生成，请稍后再分析。'
    return dict(quality, eligible=enabled() and quality['ready'] and not same and not cooldown and not detail_busy,
                status=status, reason=reason, cooldownSeconds=cooldown, windowEnd=end, snapshotId=key)


def generate_manual(store, key, end, rows, now, invoke=None, activity=None, events=None):
    date = datetime.fromtimestamp(end/1000, timezone(timedelta(hours=8))).date().isoformat()
    try:
        with store.analysis_lock():
            body = _report_body(rows, end, 'manual24h', date, now, invoke, 'manual:'+key,
                                activity if activity is not None else store.activity_snapshot(end-2*DAY,end,now),
                                events if events is not None else store.events(end-2*DAY,end),store.recent_evidence_topics())
        store.finish_manual(key, now_ms(), body=body)
    except Exception as error:
        code = str(error) if isinstance(error, AnalysisError) else 'analysis_internal_error'
        store.finish_manual(key, now_ms(), error_code=code)


def request_manual(store, now=None, launch=None):
    now = now if now is not None else now_ms()
    rows = store.readings(now-366*DAY, now)
    end = rows[-1]['sourceAt'] if rows else now
    activity = store.activity_snapshot(end-2*DAY,end,now)
    events = store.event_snapshot(end-2*DAY,end)
    status = manual_status(store, now, points=rows, activity=activity, events=events)
    if not status['eligible']:
        return (200 if status['status'] in ('ready', 'running') else 409), status
    key, end = status['snapshotId'], status['windowEnd']
    claimed = store.claim_manual(key, end, now)
    if claimed != 'created':
        return (200 if claimed == 'existing' else 409), manual_status(store, now)
    def run():
        generate_manual(store, key, end, rows, now, activity=activity, events=events['events'])
    try:
        if launch is None:
            threading.Thread(target=run, name='ottai-manual-analysis', daemon=True).start()
        else:
            launch(run)
    except Exception:
        store.finish_manual(key, now_ms(), error_code='analysis_launch_failed')
        return 503, {'status': 'error', 'reason': '分析暂时无法启动。'}
    return 202, dict(status='running', reason='正在分析最近24小时；可继续正常使用。')
