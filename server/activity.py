"""Read-only Health Connect snapshots and descriptive glucose/activity alignment.

Intervals are half-open [startAt, endAt); HR samples retain original timestamps.
Snapshots reconcile native Health Connect record START times in [windowStart, windowEnd).
No activity is inferred from heart rate alone, and no daily total is spread in time.
"""
import json
import math
from datetime import datetime, timedelta, timezone

from .statistics import DAY, MINUTE, metrics

KINDS = ('exercise', 'heart_rate', 'steps')
SOURCE = 'health_connect'
ORIGIN = 'com.mi.health'
MAX_ACTIVITY_BODY = 4 * 1024 * 1024
MAX_RECORDS = 10000
MAX_SAMPLES = 100000
MAX_WINDOW = 31 * DAY

# Only these static categories may leave the validator; never rejected values.
ACTIVITY_VALIDATION_REASONS = frozenset(['Activity record limit', 'Duplicate or unsupported activity origin', 'Heart rate sample limit', 'Invalid activity availability', 'Invalid activity fields', 'Invalid activity identifier', 'Invalid activity interval', 'Invalid activity kind', 'Invalid activity record', 'Invalid activity snapshot', 'Invalid activity timestamp', 'Invalid activity window', 'Invalid app version code', 'Invalid app version name', 'Invalid device description', 'Invalid device metadata', 'Invalid device type', 'Invalid exercise type', 'Invalid heart rate sample', 'Invalid heart rate sample list', 'Invalid heart rate value or order', 'Invalid origin app metadata', 'Invalid readable kinds', 'Invalid recording method', 'Invalid step count', 'Invalid timezone offset', 'Unavailable snapshots must not contain data', 'Invalid activity timestamp: syncedAt', 'Invalid activity timestamp: windowStart', 'Invalid activity timestamp: windowEnd', 'Invalid activity timestamp: startAt', 'Invalid activity timestamp: endAt', 'Invalid activity timestamp: modifiedAt', 'Invalid activity timestamp: sample.time'])


class ActivityValidationError(ValueError):
    def __init__(self, reason):
        reason = reason if reason in ACTIVITY_VALIDATION_REASONS else 'Invalid activity snapshot'
        super().__init__(reason)


# Native framework ExerciseSessionType values, NOT androidx/Jetpack constants.
# Verified against the official Android API 35 android.jar public ConstantValues.
# https://developer.android.com/reference/android/health/connect/datatypes/ExerciseSessionType
EXERCISE_TYPE_LABELS = {
    0: '未知运动', 1: '羽毛球', 2: '棒球', 3: '篮球', 4: '骑行', 5: '固定自行车',
    9: '板球', 10: '舞蹈', 20: '间歇训练（原始类型标签）', 21: '徒步', 27: '普拉提',
    33: '跑步', 34: '跑步机跑步', 45: '力量训练', 46: '拉伸',
    48: '开放水域游泳', 49: '泳池游泳', 53: '步行', 55: '举重',
    56: '轮椅活动', 57: '瑜伽', 58: '其他锻炼', 60: '椭圆机', 61: '划船机',
}


def exercise_type_label(code):
    return EXERCISE_TYPE_LABELS.get(code, '其他运动（类型代码%d）' % code)


def _shanghai_time(at):
    # The existing reporting contract is Asia/Shanghai (UTC+08:00), independent
    # of the server's locale/timezone; no model-side epoch conversion is needed.
    return datetime.fromtimestamp(at/1000, timezone(timedelta(hours=8))).isoformat(timespec='seconds')



def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _timestamp(value, now, field, future_tolerance=90000):
    if type(value) is not int or not 0 < value <= now + future_tolerance:
        raise ActivityValidationError('Invalid activity timestamp: '+field)
    return value


def validate_activity(payload, now):
    fields = {'source', 'syncedAt', 'windowStart', 'windowEnd', 'status', 'readableKinds', 'records'}
    if not isinstance(payload, dict) or not fields <= set(payload) or set(payload)-fields-{'originApp'} or payload['source'] != SOURCE:
        raise ActivityValidationError('Invalid activity snapshot')
    synced = _timestamp(payload['syncedAt'], now, 'syncedAt')
    start, end = _timestamp(payload['windowStart'], now, 'windowStart'), _timestamp(payload['windowEnd'], now, 'windowEnd')
    if not start < end or end-start > MAX_WINDOW or end > synced+90000:
        raise ActivityValidationError('Invalid activity window')
    status, kinds = payload['status'], payload['readableKinds']
    if status not in ('available', 'permission_denied', 'unavailable'):
        raise ActivityValidationError('Invalid activity availability')
    if not isinstance(kinds, list) or len(kinds) > 3 or any(k not in KINDS for k in kinds) or len(set(kinds)) != len(kinds):
        raise ActivityValidationError('Invalid readable kinds')
    rows = payload['records']
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise ActivityValidationError('Activity record limit')
    if (status == 'available' and not kinds) or (status != 'available' and (kinds or rows)):
        raise ActivityValidationError('Unavailable snapshots must not contain data')
    origin_app = payload.get('originApp')
    if origin_app is not None:
        if not isinstance(origin_app, dict) or set(origin_app)-{'packageName','versionName','versionCode'} or origin_app.get('packageName') != ORIGIN:
            raise ActivityValidationError('Invalid origin app metadata')
        if 'versionName' in origin_app and (not isinstance(origin_app['versionName'], str) or len(origin_app['versionName']) > 80 or any(ord(c) < 32 for c in origin_app['versionName'])):
            raise ActivityValidationError('Invalid app version name')
        if 'versionCode' in origin_app and (type(origin_app['versionCode']) is not int or not 0 <= origin_app['versionCode'] < 2**63):
            raise ActivityValidationError('Invalid app version code')
    normalized, seen, sample_count = [], set(), 0
    common = {'id', 'kind', 'origin', 'startAt', 'endAt', 'modifiedAt', 'recordingMethod', 'device', 'startOffsetSeconds', 'endOffsetSeconds'}
    optional = {'device', 'startOffsetSeconds', 'endOffsetSeconds'}
    for row in rows:
        if not isinstance(row, dict):
            raise ActivityValidationError('Invalid activity record')
        kind = row.get('kind')
        if not isinstance(kind, str):
            raise ActivityValidationError('Invalid activity kind')
        extra = {'heart_rate': {'samples'}, 'steps': {'count'}, 'exercise': {'exerciseType'}}.get(kind)
        if extra is None or set(row)-common-extra or not (common-optional | extra) <= set(row):
            raise ActivityValidationError('Invalid activity fields')
        identifier = row['id']
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200 or any(ord(c) < 32 for c in identifier):
            raise ActivityValidationError('Invalid activity identifier')
        if identifier in seen or kind not in kinds or row['origin'] != ORIGIN:
            raise ActivityValidationError('Duplicate or unsupported activity origin')
        seen.add(identifier)
        # Native interval containers may end at a future day boundary; samples remain strict.
        a, b = _timestamp(row['startAt'], now, 'startAt'), _timestamp(row['endAt'], synced, 'endAt', MAX_WINDOW)
        modified = _timestamp(row['modifiedAt'], now, 'modifiedAt')
        if not a <= b or b-a > MAX_WINDOW or not (start <= a < end) or modified > synced+90000:
            raise ActivityValidationError('Invalid activity interval')
        method = row['recordingMethod']
        if type(method) is not int or not 0 <= method <= 3:
            raise ActivityValidationError('Invalid recording method')
        item = {k: row[k] for k in common-{'device'} if k in row}
        for key in ('startOffsetSeconds','endOffsetSeconds'):
            if key in row and (type(row[key]) is not int or not -64800 <= row[key] <= 64800):
                raise ActivityValidationError('Invalid timezone offset')
        if 'device' in row:
            device = row['device']
            if not isinstance(device, dict) or set(device)-{'manufacturer', 'model', 'type'}:
                raise ActivityValidationError('Invalid device metadata')
            for key in ('manufacturer', 'model'):
                if key in device and (not isinstance(device[key], str) or len(device[key]) > 120 or any(ord(c) < 32 for c in device[key])):
                    raise ActivityValidationError('Invalid device description')
            if 'type' in device and (type(device['type']) is not int or not 0 <= device['type'] <= 100):
                raise ActivityValidationError('Invalid device type')
            item['device'] = dict(device)
        if kind == 'heart_rate':
            samples = row['samples']
            if not isinstance(samples, list):
                raise ActivityValidationError('Invalid heart rate sample list')
            sample_count += len(samples)
            if sample_count > MAX_SAMPLES:
                raise ActivityValidationError('Heart rate sample limit')
            normalized_samples = []
            for point in samples:
                if not isinstance(point, dict) or set(point) != {'time', 'bpm'}:
                    raise ActivityValidationError('Invalid heart rate sample')
                at = _timestamp(point['time'], now, 'sample.time')
                bpm = point['bpm']
                if not a <= at <= b or type(bpm) not in (int, float) or not 0 < bpm <= 300 or not math.isfinite(bpm):
                    raise ActivityValidationError('Invalid heart rate value or order')
                normalized_samples.append({'time': at, 'bpm': bpm})
            item['samples'] = sorted(normalized_samples, key=lambda p: (p['time'],p['bpm']))
        elif kind == 'steps':
            if type(row['count']) is not int or not 0 <= row['count'] <= 2000000:
                raise ActivityValidationError('Invalid step count')
            item['count'] = row['count']
        else:
            if type(row['exerciseType']) is not int or not 0 <= row['exerciseType'] <= 1000:
                raise ActivityValidationError('Invalid exercise type')
            item['exerciseType'] = row['exerciseType']
        normalized.append(item)
    normalized.sort(key=lambda r: r['id'])
    result = dict(source=SOURCE, syncedAt=synced, windowStart=start, windowEnd=end,
                  status=status, readableKinds=sorted(kinds), records=normalized)
    if origin_app is not None:
        result['originApp'] = dict(origin_app)
    return result


def activity_view(snapshot, start, end, now):
    state = snapshot['state']
    cutoff = min(end,now)
    records = [r for r in snapshot['records'] if r['startAt'] < end and r['startAt'] <= cutoff
               and (r['endAt'] > start or r['startAt']==r['endAt'] and r['startAt']>=start)]
    status = state.get('status', 'not_connected')
    kinds = state.get('readableKinds', [])
    stale = status != 'available' or state.get('lastSyncedAt') is None or now-state['lastSyncedAt'] > 30*MINUTE
    sessions = [r for r in records if r['kind'] == 'exercise']
    steps = [dict(r, temporalResolution=('instant_count' if r['endAt']==r['startAt'] else 'interval' if r['endAt']-r['startAt'] <= 15*MINUTE else 'coarse_total'))
             for r in records if r['kind'] == 'steps']
    hr = []
    for record in records:
        if record['kind'] == 'heart_rate':
            hr.extend(dict(p, recordId=record['id']) for p in record['samples'] if start <= p['time'] < end and p['time'] <= now)
    raw_hr_count = len(hr)
    by_time = {}
    for point in hr:
        by_time.setdefault(point['time'], []).append(point)
    hr_conflicts = sum(len(set(p['bpm'] for p in points)) > 1 for points in by_time.values())
    hr_duplicate_times = sum(len(points) > 1 for points in by_time.values())
    # Equal duplicates collapse; conflicting simultaneous readings are ambiguous,
    # so do not invent a fused sensor value or give repeated records extra weight.
    hr = [dict(points[0], recordIds=sorted(set(p['recordId'] for p in points)))
          for at, points in sorted(by_time.items()) if len(set(p['bpm'] for p in points)) == 1]
    # Never silently sum overlapping records from different devices, or prorate an edge interval.
    ordered = sorted(steps, key=lambda r: (r['startAt'], r['endAt']))
    instant_steps = any(r['startAt']==r['endAt'] for r in steps)
    overlapping = instant_steps or any(a['endAt'] > b['startAt'] for a, b in zip(ordered, ordered[1:]))
    fully_inside = all(start <= r['startAt'] and r['endAt'] <= cutoff for r in steps)
    steps_readable = status == 'available' and 'steps' in kinds and not stale
    limitations = ['空白时段表示没有可用记录，不代表静止、未运动或心率为零。',
                   '步数按原始区间保留；粗粒度总量不均摊到分钟。心率不单独用于确认运动。',
                   '同步窗口按原生Health Connect记录开始时间读取；窗口前已开始的跨界记录可能未被首次读到。']
    if any(cutoff < r['startAt'] < end for r in snapshot['records']):
        limitations.append('部分记录起点超出当前时刻，尚未纳入本次观测。')
    if any(r['endAt'] > cutoff for r in records):
        limitations.append('部分源记录结束时间超出观察截止；只使用已收到的样本或实际覆盖，不认定记录已完整结束。')
    if status != 'available':
        limitations.append('活动资料当前不可读或尚未连接；历史缓存不能代表当前活动。')
    if set(kinds) != set(KINDS):
        limitations.append('部分活动类型未获读取权限或不受支持；缺失类型不能按零处理。')
    if stale:
        limitations.append('活动同步超过30分钟或尚未完成；活动资料可能滞后。')
    if overlapping or not fully_inside:
        limitations.append('步数区间存在潜在重叠、零时长或跨观察边界，不计算可能重复或分摊的总步数。')
    query_coverage = {k: round(sum(max(0,min(end,b)-max(start,a)) for a,b in snapshot.get('coverage', {}).get(k, []))/MINUTE, 2) for k in KINDS}
    if hr_duplicate_times:
        limitations.append('存在同时间的多条心率记录：相同值合并，不同值不作自动融合。')
    summary = {'recordedExerciseCount': len(sessions) if 'exercise' in kinds and status=='available' else None,
               'heartRateSampleCount': len(hr), 'rawHeartRateSampleCount': raw_hr_count,
               'potentialHeartRateOverlap': bool(hr_duplicate_times), 'conflictingHeartRateTimes': hr_conflicts,
               'potentialStepOverlap': overlapping, 'zeroDurationRecordCount': sum(r['startAt']==r['endAt'] for r in records),
               'stepRecordCount': len(steps), 'coarseStepRecordCount': sum(r['temporalResolution']=='coarse_total' for r in steps),
               'observedStepTotal': sum(r['count'] for r in steps) if steps_readable and steps and not overlapping and fully_inside else None,
               'heartRateMin': min((p['bpm'] for p in hr), default=None),
               'heartRateMax': max((p['bpm'] for p in hr), default=None)}
    return dict(source=SOURCE, origin=ORIGIN, originApp=state.get('originApp'), status=status, readableKinds=kinds, stale=stale,
                lastSyncedAt=state.get('lastSyncedAt'), lastSuccessfulSyncAt=state.get('lastSuccessfulSyncAt'),
                windowStart=start, windowEnd=end, sourceWindowStart=state.get('windowStart'),
                sourceWindowEnd=state.get('windowEnd'), queryCoverageMinutes=query_coverage,
                queryCoverageMeaning='按记录开始时间成功查询过的窗口，不等于佩戴、运动或心率样本覆盖', exerciseSessions=sessions, heartRate=hr,
                stepIntervals=steps, summary=summary, limitations=limitations)


def _heart_rate_stats(points):
    values = [p['bpm'] for p in points]
    return {'sampleCount': len(values), 'meanBpm': round(sum(values)/len(values),2) if values else None,
            'minBpm': min(values) if values else None, 'maxBpm': max(values) if values else None}


def _analysis_heart_rate(view, start, end, now):
    # Observed points only, with minutes before this context period end as the explicit time basis.
    bins = {}
    for point in view['heartRate']:
        index = int((point['time']-start)//(15*MINUTE))
        bins.setdefault(index, []).append(point)
    rows = []
    for index, points in sorted(bins.items()):
        stats = _heart_rate_stats(points)
        rows.append([round((end-start)/MINUTE-index*15,3), max(0,round((end-start)/MINUTE-(index+1)*15,3)),
                     round((end-points[0]['time'])/MINUTE,3), round((end-points[-1]['time'])/MINUTE,3),
                     stats['meanBpm'],stats['minBpm'],stats['maxBpm'],stats['sampleCount']])
    points = view['heartRate']
    first, last = (points[0]['time'],points[-1]['time']) if points else (None,None)
    return {'columns': ['binStartMinutesBeforeEnd','binEndMinutesBeforeEnd','firstSampleMinutesBeforeEnd','lastSampleMinutesBeforeEnd','meanBpm','minBpm','maxBpm','sampleCount'],
            'timeBasis': 'minutes_before_this_periodEnd', 'rowOrder': 'earliest_to_latest; start/first minutes >= end/last minutes', 'binMinutes': 15, 'rows': rows[:96], 'truncated': len(rows)>96,
            'firstSampleAt': first, 'lastSampleAt': last,
            'firstSampleLocal': _shanghai_time(first) if first is not None else None,
            'lastSampleLocal': _shanghai_time(last) if last is not None else None,
            'lastSampleAgeAtReportMinutes': round(max(0,now-last)/MINUTE,1) if last is not None else None,
            'lastSampleAgeAtPeriodEndMinutes': round(max(0,end-last)/MINUTE,1) if last is not None else None,
            'meaning': '只汇总真实观测样本，不插值；空时段不代表心率为零、静止或未运动，采样均值不是时间加权心率。'}


def analysis_context(snapshot, readings, start, end, now, excursions=None):
    """Bounded descriptive context; all windows below are product observation choices."""
    view = activity_view(snapshot, start, end, now)
    sessions = sorted(view['exerciseSessions'], key=lambda r: r['startAt'])
    observations = []
    def window(a, b):
        if a >= b:
            return None
        measured = metrics(readings,a,b)
        # Core evidence only: repeated labels/reference boilerplate add no signal
        # across up to 48 sessions and can crowd out actual time-series samples.
        fields = ('periodStart','periodEnd','sampleCount','observedMinutes','expectedMinutes','coveragePercent',
                  'mean','sd','cvPercent','min','max','inRangePercent','belowRangePercent','aboveRangePercent','limitations')
        return {key:measured[key] for key in fields}
    for record in sessions[:24]:
        a, b = max(start, record['startAt']), min(end, now, record['endAt'])
        censored = record['endAt'] > min(end,now)
        session_hr = [p for p in view['heartRate'] if record['startAt'] <= p['time'] < min(record['endAt'],end,now)]
        observations.append({'startAt': record['startAt'], 'endAt': record['endAt'],
                             'startLocal': _shanghai_time(record['startAt']), 'endLocal': _shanghai_time(record['endAt']),
                             'timezone': 'Asia/Shanghai',
                             'endBeyondObservationWindow': record['endAt'] > end, 'endCensored': censored,
                             'observedStartAt': a, 'observedEndAt': b,
                             'observedEndLocal': _shanghai_time(b),
                             'exerciseType': record['exerciseType'], 'exerciseTypeLabel': exercise_type_label(record['exerciseType']),
                             'recordingMethod': record['recordingMethod'],
                             'origin': record['origin'], 'device': record.get('device'),
                             'observedHeartRateSampleCount': len(session_hr),
                             'observedHeartRateStats': _heart_rate_stats(session_hr),
                             'candidateExcursionOverlapCount': sum(record['startAt'] < event['endAt'] and record['endAt'] > event['riseStartAt']
                                                                    for event in (excursions or {}).get('events', [])),
                             'glucoseBefore30m': window(max(start, a-30*MINUTE), a),
                             'glucoseDuring': window(a, b),
                             'glucoseAfter60m': None if censored else window(b, min(end, b+60*MINUTE))})
    # HR remains descriptive of available samples, not intensity or a continuous coverage estimate.
    return {'source': SOURCE, 'origin': ORIGIN, 'originApp': view['originApp'], 'periodStart': start, 'periodEnd': end, 'timezone': 'Asia/Shanghai',
            'availability': {k: view[k] for k in ('status', 'readableKinds', 'stale', 'lastSyncedAt',
                                                'lastSuccessfulSyncAt', 'sourceWindowStart', 'sourceWindowEnd')},
            'queryCoverageMinutes': view['queryCoverageMinutes'], 'queryCoverageMeaning': view['queryCoverageMeaning'],
            'summary': view['summary'], 'heartRateTimeline': _analysis_heart_rate(view,start,end,now),
            'recordedSessions': observations,
            'sessionsTruncated': len(sessions) > 24,
            'shortStepIntervals': [{'startAt': r['startAt'], 'endAt': r['endAt'], 'count': r['count']}
                                   for r in view['stepIntervals'] if r['temporalResolution']=='interval'][:288],
            'shortStepIntervalsTruncated': sum(r['temporalResolution']=='interval' for r in view['stepIntervals']) > 288,
            'limitations': view['limitations'] + ['运动前30分钟/中/后60分钟为描述性产品窗口，未经临床验证；覆盖不足时不可比较。',
                                                '记录运动与血糖变化的时间关联不证明因果、饮食质量或代谢/激素功能变化。']}


def dashboard_activity(snapshot, start, end, now):
    """Compact public plot payload; never place 100k HR samples in a dashboard."""
    view = activity_view(snapshot, start, end, now)
    bins = {}
    for point in view['heartRate']:
        index = int((point['time']-start)//(5*MINUTE))
        bins.setdefault(index, []).append(point)
    heart_rate = []
    for index, points in sorted(bins.items()):
        values = [p['bpm'] for p in points]
        heart_rate.append(dict(startAt=start+index*5*MINUTE, endAt=min(end,start+(index+1)*5*MINUTE),
                               mean=round(sum(values)/len(values),2), min=min(values), max=max(values),
                               sampleCount=len(values), firstSampleAt=points[0]['time'], lastSampleAt=points[-1]['time']))
    sessions = view['exerciseSessions']
    intervals = view['stepIntervals']
    view['exerciseSessions'] = [dict({k:r[k] for k in ('id','startAt','endAt','exerciseType','origin','recordingMethod')},
                                     exerciseTypeLabel=exercise_type_label(r['exerciseType'])) for r in sessions[:128]]
    view['stepIntervals'] = [{k:r[k] for k in ('id','startAt','endAt','count','temporalResolution')} for r in intervals[:288]]
    view['heartRate'] = heart_rate[:288]
    view['heartRateRepresentation'] = 'observed_sample_5_minute_summary_not_raw_or_interpolated'
    view['exerciseSessionsTruncated'] = len(sessions)>128
    view['stepIntervalsTruncated'] = len(intervals)>288
    view['heartRateTruncated'] = len(heart_rate)>288
    return view
