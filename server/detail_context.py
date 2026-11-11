"""Deterministic, period-pinned observations for explicitly requested interpretation."""
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from .activity import exercise_type_label, sleep_session_context
from .detail_sources import SOURCES
from .excursions import candidate_excursions, day_quality
from .lifestyle import context as event_context
from .statistics import DAY, MINUTE, analysis_input, metrics, round_value

TZ = timezone(timedelta(hours=8))
MAX_CONTEXT_BYTES = 210000


def clock(at):
    return datetime.fromtimestamp(at / 1000, TZ).isoformat(timespec='seconds')


def compact_metrics(rows, start, end):
    if start >= end:
        return None
    value = metrics(rows, start, end)
    fields = ('periodStart', 'periodEnd', 'sampleCount', 'observedMinutes', 'expectedMinutes',
              'coveragePercent', 'mean', 'sd', 'cvPercent', 'min', 'max',
              'inRangePercent', 'belowRangePercent', 'aboveRangePercent')
    return {k: value[k] for k in fields}


def meal_profile(event, rows, end, next_meal=None):
    at = event['at']
    limit = min(end, at + 240 * MINUTE, next_meal if next_meal is not None else end)
    before = [r for r in rows if at - 30 * MINUTE <= r['sourceAt'] < at]
    after = [r for r in rows if at <= r['sourceAt'] <= limit and
             (next_meal is None or r['sourceAt'] < next_meal)]
    baseline = median([r['value'] for r in before]) if len(before) >= 3 and before[-1]['sourceAt'] - before[0]['sourceAt'] >= 10 * MINUTE else None
    peak = max(after, key=lambda r: r['value']) if after else None
    meal = event.get('meal', {})
    result = {'id': event['id'], 'at': at, 'localTime': clock(at), 'confirmedByUser': True,
              'note': event.get('note', '')[:160], 'noteTruncated': len(event.get('note', '')) > 160,
              'foods': meal.get('foods', '')[:240], 'foodsTruncated': len(meal.get('foods', '')) > 240,
              'foodSource': meal.get('source', 'manual'),
              'estimatedKcalMin': meal.get('estimatedKcalMin'), 'estimatedKcalMax': meal.get('estimatedKcalMax'),
              'premealMedian': round_value(baseline), 'premealSampleCount': len(before),
              'premealRange': round_value(max(r['value'] for r in before) - min(r['value'] for r in before)) if before else None,
              'followupEnd': limit, 'followupMinutes': round_value(max(0, limit - at) / MINUTE),
              'followupCensored': limit < at + 240 * MINUTE, 'nextMealAt': next_meal,
              'observedPeak': peak['value'] if peak else None,
              'observedPeakAt': peak['sourceAt'] if peak else None,
              'peakMinutesAfterMeal': round_value((peak['sourceAt'] - at) / MINUTE) if peak else None,
              'observedRise': round_value(peak['value'] - baseline) if peak and baseline is not None else None,
              'nearHourReadings': [], 'returnedNearBaselineAt': None,
              'returnObservationMinutesAfterMeal': None,
              'followupMetrics': compact_metrics(rows, at, limit),
              'observedPositiveAreaMmolMinPerL': None, 'integratedMinutes': 0}
    for minute in (60, 120, 180):
        target = at + minute * MINUTE
        nearest = min(after, key=lambda r: abs(r['sourceAt'] - target)) if after and target <= limit else None
        if nearest and abs(nearest['sourceAt'] - target) <= 7.5 * MINUTE:
            result['nearHourReadings'].append({'targetMinutes': minute, 'actualAt': nearest['sourceAt'],
                                             'actualMinutes': round_value((nearest['sourceAt'] - at) / MINUTE),
                                             'value': nearest['value']})
    if baseline is not None:
        area, observed = 0.0, 0.0
        for left, right in zip(after, after[1:]):
            gap = (right['sourceAt'] - left['sourceAt']) / MINUTE
            if not 0 < gap <= 10:
                continue
            a, b = left['value'] - baseline, right['value'] - baseline
            if a >= 0 and b >= 0:
                area += (a + b) * gap / 2
            elif max(a, b) > 0:
                # Positive part of the linear segment, including a baseline crossing.
                area += max(a, b) ** 2 * gap / (2 * (abs(a) + abs(b)))
            observed += gap
        result['observedPositiveAreaMmolMinPerL'] = round_value(area) if observed else None
        result['integratedMinutes'] = round_value(observed)
        if peak and peak['value'] > baseline + .3:
            later = [r for r in after if r['sourceAt'] > peak['sourceAt']]
            broken = False
            prior = peak['sourceAt']
            for index, row in enumerate(later):
                broken = broken or row['sourceAt'] - prior > 10 * MINUTE
                prior = row['sourceAt']
                if index < 2 or broken:
                    continue
                near = later[index - 2:index + 1]
                if near[-1]['sourceAt'] - near[0]['sourceAt'] >= 10 * MINUTE and all(r['value'] <= baseline + .3 for r in near):
                    result['returnedNearBaselineAt'] = near[-1]['sourceAt']
                    result['returnObservationMinutesAfterMeal'] = round_value((near[-1]['sourceAt'] - at) / MINUTE)
                    break
    return result


def _interval_summary(records, key, start, end, minutes):
    rows = sorted(records, key=lambda r: (r['startAt'], r['endAt'], r.get('id', '')))
    overlap, cursor = False, None
    for row in rows:
        overlap = overlap or row['startAt'] == row['endAt'] or cursor is not None and row['startAt'] < cursor
        cursor = max(cursor or row['endAt'], row['endAt'])
    groups = defaultdict(list)
    for row in rows:
        if 0 < row['endAt'] - row['startAt'] <= minutes * MINUTE:
            groups[(row['startAt'] - start) // (minutes * MINUTE)].append(row)
    bins = []
    for index, items in sorted(groups.items()):
        a, b = start + index * minutes * MINUTE, min(end, start + (index + 1) * minutes * MINUTE)
        bins.append({'startAt': a, 'endAt': b, 'rawIntervalSum': round_value(math.fsum(r[key] for r in items), 4),
                     'recordCount': len(items), 'firstNativeStartAt': min(r['startAt'] for r in items),
                     'lastNativeEndAt': max(r['endAt'] for r in items),
                     'crossBinCount': sum(r['endAt'] > b for r in items)})
    return {'recordCount': len(rows), 'potentialOverlap': overlap,
            'observedTotal': round_value(math.fsum(r[key] for r in rows), 4) if rows and not overlap else None,
            'coarseRecordCount': sum(r['endAt'] - r['startAt'] > minutes * MINUTE for r in rows),
            'startGroupedTimeline': bins,
            'intervalExamples': [{k: r[k] for k in ('startAt', 'endAt', key, 'origin') if k in r} for r in rows[-24:]],
            'examplesTruncated': len(rows) > 24}


def activity_window(records, start, end, readings=None):
    overlapping = [(source, r) for source, r in records if r['startAt'] < end and
                   (r['endAt'] > start or r['startAt'] == r['endAt'] and r['startAt'] >= start)]
    full = [(source, r) for source, r in overlapping if start <= r['startAt'] <= r['endAt'] <= end]
    steps = {source: [r for s, r in full if s == source and r['kind'] == 'steps'] for source in ('health_connect', 'phone_steps')}
    fine = lambda source: any(0 < r['endAt'] - r['startAt'] <= 15 * MINUTE for r in steps[source])
    selected = 'health_connect' if fine('health_connect') else 'phone_steps' if fine('phone_steps') else 'health_connect' if steps['health_connect'] else 'phone_steps' if steps['phone_steps'] else 'health_connect'
    hr = defaultdict(set)
    for source, row in overlapping:
        if source == 'health_connect' and row['kind'] == 'heart_rate':
            for sample in row['samples']:
                if start <= sample['time'] < end:
                    hr[sample['time']].add(sample['bpm'])
    bins = defaultdict(list)
    for at, values in sorted(hr.items()):
        if len(values) == 1:
            bins[(at - start) // (15 * MINUTE)].append((at, next(iter(values))))
    timeline = []
    for index, points in sorted(bins.items()):
        values = [p[1] for p in points]
        timeline.append({'startAt': start + index * 15 * MINUTE, 'endAt': min(end, start + (index + 1) * 15 * MINUTE),
                         'firstSampleAt': points[0][0], 'lastSampleAt': points[-1][0],
                         'meanBpm': round_value(sum(values) / len(values)), 'minBpm': min(values), 'maxBpm': max(values), 'sampleCount': len(values)})
    sessions = [r for source, r in overlapping if source == 'health_connect' and r['kind'] == 'exercise']
    sleep = sorted((r for source, r in overlapping if source == 'health_connect' and r['kind'] == 'sleep'),key=lambda r:(r['startAt'],r['id']))
    session_observations = []
    for row in sessions[:24]:
        a,b = max(start,row['startAt']),min(end,row['endAt'])
        censored = row['endAt']>end
        session_observations.append({'startAt':row['startAt'],'endAt':b,'origin':row['origin'],
                                     'startLocal':clock(row['startAt']),'endLocal':clock(b),
                                     'observedStartAt':a,'observedEndAt':b,'endCensored':censored,
                                     'exerciseType':row['exerciseType'],'exerciseTypeLabel':exercise_type_label(row['exerciseType']),
                                     'glucoseBefore30m':compact_metrics(readings or [],max(start,a-30*MINUTE),a),
                                     'glucoseDuring':compact_metrics(readings or [],a,b),
                                     'glucoseAfter60m':None if censored else compact_metrics(readings or [],b,min(end,b+60*MINUTE))})
    return {'periodStart': start, 'periodEnd': end, 'stepsSource': selected,
            'selectionMeaning': '仅使用该历史时段的实际记录，HC细区间优先、其次手机细区间、再粗总量；不使用当前同步状态，不合并步数来源。',
            'sourceOrigins': sorted(set(r['origin'] for _, r in overlapping if r['kind'] != 'heart_rate') |
                                    set(r['origin'] for source, r in overlapping if source == 'health_connect' and r['kind'] == 'heart_rate' and any(start <= p['time'] < end for p in r['samples']))),
            'heartRateTimeline': timeline, 'heartRateSampleCount': sum(p['sampleCount'] for p in timeline),
            'conflictingHeartRateTimestamps': sum(len(v) > 1 for v in hr.values()),
            'steps': _interval_summary(steps[selected], 'count', start, end, 15),
            'activeCalories': _interval_summary([r for s, r in full if s == 'health_connect' and r['kind'] == 'active_calories'], 'energyKcal', start, end, 30),
            'sessions': session_observations,
            'sessionsTruncated': len(sessions) > 24,
            'sleepSessions':sleep_session_context(sleep,readings or [],start,end,end),
            'sleepSessionsTruncated':len(sleep)>32,'sleepSessionTotalCount':len(sleep),
            'potentialSleepSessionOverlap':any(a['endAt']>b['startAt'] for a,b in zip(sleep,sleep[1:])),
            'sleepSessionMeaning':'Health Connect原始睡眠会话，可能包含清醒片段；只统计报告窗口内交集血糖，不将区间时长当实际睡着时长，不与手动入睡/起床标记合并。',
            'crossBoundaryOmitted': {kind: sum(r['kind'] == kind and not start <= r['startAt'] <= r['endAt'] <= end for _, r in overlapping)
                                     for kind in ('steps', 'active_calories', 'exercise')},
            'meaning': '心率仅为实际样本；步数/热量按原区间起点分组不均摊。跨界总量未计入，空白不是静止，热量不是精确消耗或独立于心率的证据。'}


def _sleep_pairs(events, start, end):
    pending, pairs = None, []
    for event in events:
        if event['type'] == 'sleep':
            pending = event['at']
        elif event['type'] == 'wake' and pending is not None:
            if 0 < event['at'] - pending <= 20 * 60 * MINUTE and event['at'] > start:
                pairs.append({'sleepAt': pending, 'wakeAt': event['at'],
                              'reportedHours': round_value((event['at'] - pending) / 3600000)})
            pending = None
    return {'pairs': pairs[-14:], 'unpairedSleepAt': pending if pending is not None and pending >= start else None,
            'meaning': '用户报告的近似区间，不是已测睡眠质量。'}


def build_context(store, parent, now):
    end, start = parent['periodEnd'], parent['periodStart']
    if type(end) is not int or type(start) is not int or end - start != DAY:
        raise ValueError('invalid_detail_window')
    kind = parent.get('kind') or ('daily' if parent.get('trigger') == 'scheduled_daily' else 'rolling')
    rows = store.readings(end - 366 * DAY, end - 1 if kind == 'daily' else end)
    glucose = analysis_input(rows, end)
    glucose['profile'] = '用户提供信息见patient；诊断、药物和实验室资料未提供的部分均未知。'
    glucose['previous24hReadingColumns'] = ['minutesBeforePeriodEnd', 'mmolPerL']
    glucose['previous24hReadings'] = [[round_value((end - r['sourceAt']) / MINUTE, 1), r['value']] for r in rows if end - 2 * DAY <= r['sourceAt'] < start]
    events = store.events(end - 29 * DAY, end - 1, 1001)
    events_truncated = len(events) > 1000
    events = events[-1000:]
    meals = [e for e in events if e['type'] == 'meal']
    chosen = []
    counts = {}
    for label, a, b in [('latest24h', start, end), ('previous24h', start - DAY, start), ('earlier28d', end - 29 * DAY, start - DAY)]:
        matches = [e for e in meals if a <= e['at'] < b]
        counts[label] = {'total': len(matches), 'selected': min(len(matches), 8)}
        for meal in matches[-8:]:
            following = next((e['at'] for e in meals if e['at'] > meal['at']), None)
            chosen.append(dict(meal_profile(meal, rows, end, following), comparisonGroup=label))
    with store.connect() as db:
        activity = [(r['source'], json.loads(r['body'])) for r in db.execute(
            'SELECT source,body FROM activity_records WHERE start_at<? AND end_at>=? ORDER BY start_at,record_id', (end, end - 2 * DAY))]
    midnight = datetime.fromtimestamp(end / 1000, TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    nights = []
    for offset in range(6, -1, -1):
        a = int((midnight - timedelta(days=offset)).timestamp() * 1000)
        b = min(end, a + 6 * 60 * MINUTE)
        if a >= b:
            continue
        m = compact_metrics(rows, a, b)
        if m['sampleCount']:
            nights.append({'startAt': a, 'endAt': b, 'startLocal': clock(a), 'metrics': m,
                           'confirmedMealsInOrSixHoursBefore': sum(a - 6 * 60 * MINUTE <= e['at'] < b for e in meals)})
    result = {'schemaVersion': 1,
              'window': {'kind': kind, 'periodStart': start, 'periodEnd': end,
                         'startLocal': clock(start), 'endLocal': clock(end), 'timezone': 'Asia/Shanghai',
                         'focus': '最近餐次、当前变化与短期可验证调整；历史作为参照' if kind == 'rolling' else '固定自然日作为锚点，比较7/14天及更早趋势、重复模式、改善原因与保持办法'},
              'patient': {'providedContext': os.environ.get('DETAIL_PATIENT_CONTEXT', '成人观察；诊断、用药及实验室资料未知。')[:2000]},
              'briefSummaryToVerify': parent.get('summary', '')[:500], 'glucose': glucose,
              'latest24hQuality': day_quality(rows, end), 'previous24hQuality': day_quality(rows, start),
              'candidateExcursions': candidate_excursions(rows, start, end),
              'previous24hExcursions': candidate_excursions(rows, start - DAY, start),
              'lifestyle': {'latest24h': event_context([e for e in events if start <= e['at'] < end], start, end),
                            'previous24h': event_context([e for e in events if start - DAY <= e['at'] < start], start - DAY, start),
                            'queryTruncated': events_truncated, 'sleepPairs': _sleep_pairs(events, end - 14 * DAY, end)},
              'confirmedMeals': chosen, 'mealSelection': counts,
              'mealMethod': '餐前30min至少3个点且跨度10min才取中位基线；邻近小时取±7.5min真实采样，附实际时间；正增量面积只连接≤10min邻点，跨基线分段积分，不外推缺口；观测回到基线+0.3需3点跨度10min且峰后无>10min缺口；均为描述性产品指标。下一餐/报告截止截断跟踪。',
              'nightProfiles': nights, 'nightMeaning': '00–06时钟窗口，不等于空腹或已确认睡眠。',
              'activity': {'latest24h': activity_window(activity, start, end, rows), 'previous24h': activity_window(activity, start - DAY, start, rows)},
              'sourceCatalog': SOURCES, 'contextTruncation': []}
    # Dense device records are summarized before this bound; trim only examples, never raw storage.
    size = lambda: len(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
    if size() > MAX_CONTEXT_BYTES:
        for group in result['activity'].values():
            for key in ('steps', 'activeCalories'):
                group[key]['intervalExamples'] = []
                group[key]['examplesTruncated'] = group[key]['recordCount'] > 0
        result['contextTruncation'].append('活动原区间例子省略，分时汇总与总量保留。')
    if size() > MAX_CONTEXT_BYTES:
        result['confirmedMeals'] = [m for m in chosen if m['comparisonGroup'] != 'earlier28d']
        result['contextTruncation'].append('较早餐次例子省略，历史统计保留。')
    if size() > MAX_CONTEXT_BYTES:
        raise ValueError('detail_context_limit')
    return result
