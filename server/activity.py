"""Read-only Health Connect snapshots and descriptive glucose/activity alignment.

Intervals are half-open [startAt, endAt); HR samples retain original timestamps.
Snapshots reconcile native Health Connect record START times in [windowStart, windowEnd).
No activity is inferred from heart rate alone, and no daily total is spread in time.
"""
import json
import math

from .statistics import DAY, MINUTE, metrics

KINDS = ('exercise', 'heart_rate', 'steps')
SOURCE = 'health_connect'
ORIGIN = 'com.mi.health'
MAX_ACTIVITY_BODY = 4 * 1024 * 1024
MAX_RECORDS = 10000
MAX_SAMPLES = 100000
MAX_WINDOW = 31 * DAY

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



def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _timestamp(value, now):
    if type(value) is not int or not 0 < value <= now + 90000:
        raise ValueError('Invalid activity timestamp')
    return value


def validate_activity(payload, now):
    fields = {'source', 'syncedAt', 'windowStart', 'windowEnd', 'status', 'readableKinds', 'records'}
    if not isinstance(payload, dict) or not fields <= set(payload) or set(payload)-fields-{'originApp'} or payload['source'] != SOURCE:
        raise ValueError('Invalid activity snapshot')
    synced = _timestamp(payload['syncedAt'], now)
    start, end = _timestamp(payload['windowStart'], now), _timestamp(payload['windowEnd'], now)
    if not start < end or end-start > MAX_WINDOW or end > synced+90000:
        raise ValueError('Invalid activity window')
    status, kinds = payload['status'], payload['readableKinds']
    if status not in ('available', 'permission_denied', 'unavailable'):
        raise ValueError('Invalid activity availability')
    if not isinstance(kinds, list) or len(kinds) > 3 or any(k not in KINDS for k in kinds) or len(set(kinds)) != len(kinds):
        raise ValueError('Invalid readable kinds')
    rows = payload['records']
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise ValueError('Activity record limit')
    if (status == 'available' and not kinds) or (status != 'available' and (kinds or rows)):
        raise ValueError('Unavailable snapshots must not contain data')
    origin_app = payload.get('originApp')
    if origin_app is not None:
        if not isinstance(origin_app, dict) or set(origin_app)-{'packageName','versionName','versionCode'} or origin_app.get('packageName') != ORIGIN:
            raise ValueError('Invalid origin app metadata')
        if 'versionName' in origin_app and (not isinstance(origin_app['versionName'], str) or len(origin_app['versionName']) > 80 or any(ord(c) < 32 for c in origin_app['versionName'])):
            raise ValueError('Invalid app version name')
        if 'versionCode' in origin_app and (type(origin_app['versionCode']) is not int or not 0 <= origin_app['versionCode'] < 2**63):
            raise ValueError('Invalid app version code')
    normalized, seen, sample_count = [], set(), 0
    common = {'id', 'kind', 'origin', 'startAt', 'endAt', 'modifiedAt', 'recordingMethod', 'device', 'startOffsetSeconds', 'endOffsetSeconds'}
    optional = {'device', 'startOffsetSeconds', 'endOffsetSeconds'}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid activity record')
        kind = row.get('kind')
        if not isinstance(kind, str):
            raise ValueError('Invalid activity kind')
        extra = {'heart_rate': {'samples'}, 'steps': {'count'}, 'exercise': {'exerciseType'}}.get(kind)
        if extra is None or set(row)-common-extra or not (common-optional | extra) <= set(row):
            raise ValueError('Invalid activity fields')
        identifier = row['id']
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200 or any(ord(c) < 32 for c in identifier):
            raise ValueError('Invalid activity identifier')
        if identifier in seen or kind not in kinds or row['origin'] != ORIGIN:
            raise ValueError('Duplicate or unsupported activity origin')
        seen.add(identifier)
        a, b = _timestamp(row['startAt'], now), _timestamp(row['endAt'], now)
        modified = _timestamp(row['modifiedAt'], now)
        if not a <= b or b-a > MAX_WINDOW or not (start <= a < end) or modified > synced+90000:
            raise ValueError('Invalid activity interval')
        method = row['recordingMethod']
        if type(method) is not int or not 0 <= method <= 3:
            raise ValueError('Invalid recording method')
        item = {k: row[k] for k in common-{'device'} if k in row}
        for key in ('startOffsetSeconds','endOffsetSeconds'):
            if key in row and (type(row[key]) is not int or not -64800 <= row[key] <= 64800):
                raise ValueError('Invalid timezone offset')
        if 'device' in row:
            device = row['device']
            if not isinstance(device, dict) or set(device)-{'manufacturer', 'model', 'type'}:
                raise ValueError('Invalid device metadata')
            for key in ('manufacturer', 'model'):
                if key in device and (not isinstance(device[key], str) or len(device[key]) > 120 or any(ord(c) < 32 for c in device[key])):
                    raise ValueError('Invalid device description')
            if 'type' in device and (type(device['type']) is not int or not 0 <= device['type'] <= 100):
                raise ValueError('Invalid device type')
            item['device'] = dict(device)
        if kind == 'heart_rate':
            samples = row['samples']
            if not isinstance(samples, list):
                raise ValueError('Invalid heart rate sample list')
            sample_count += len(samples)
            if sample_count > MAX_SAMPLES:
                raise ValueError('Heart rate sample limit')
            normalized_samples = []
            for point in samples:
                if not isinstance(point, dict) or set(point) != {'time', 'bpm'}:
                    raise ValueError('Invalid heart rate sample')
                at = _timestamp(point['time'], now)
                bpm = point['bpm']
                if not a <= at <= b or type(bpm) not in (int, float) or not 0 < bpm <= 300 or not math.isfinite(bpm):
                    raise ValueError('Invalid heart rate value or order')
                normalized_samples.append({'time': at, 'bpm': bpm})
            item['samples'] = sorted(normalized_samples, key=lambda p: (p['time'],p['bpm']))
        elif kind == 'steps':
            if type(row['count']) is not int or not 0 <= row['count'] <= 2000000:
                raise ValueError('Invalid step count')
            item['count'] = row['count']
        else:
            if type(row['exerciseType']) is not int or not 0 <= row['exerciseType'] <= 1000:
                raise ValueError('Invalid exercise type')
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
    records = [r for r in snapshot['records'] if r['startAt'] < end and (r['endAt'] > start or r['startAt']==r['endAt'] and r['startAt']>=start)]
    status = state.get('status', 'not_connected')
    kinds = state.get('readableKinds', [])
    stale = status != 'available' or state.get('lastSyncedAt') is None or now-state['lastSyncedAt'] > 30*MINUTE
    sessions = [r for r in records if r['kind'] == 'exercise']
    steps = [dict(r, temporalResolution=('instant_count' if r['endAt']==r['startAt'] else 'interval' if r['endAt']-r['startAt'] <= 15*MINUTE else 'coarse_total'))
             for r in records if r['kind'] == 'steps']
    hr = []
    for record in records:
        if record['kind'] == 'heart_rate':
            hr.extend(dict(p, recordId=record['id']) for p in record['samples'] if start <= p['time'] < end)
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
    fully_inside = all(start <= r['startAt'] and r['endAt'] <= end for r in steps)
    steps_readable = status == 'available' and 'steps' in kinds and not stale
    limitations = ['空白时段表示没有可用记录，不代表静止、未运动或心率为零。',
                   '步数按原始区间保留；粗粒度总量不均摊到分钟。心率不单独用于确认运动。',
                   '同步窗口按原生Health Connect记录开始时间读取；窗口前已开始的跨界记录可能未被首次读到。']
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


def analysis_context(snapshot, readings, start, end, now, excursions=None):
    """Bounded descriptive context; all windows below are product observation choices."""
    view = activity_view(snapshot, start, end, now)
    sessions = sorted(view['exerciseSessions'], key=lambda r: r['startAt'])
    observations = []
    def window(a, b):
        return metrics(readings, a, b) if a < b else None
    for record in sessions[:24]:
        a, b = max(start, record['startAt']), min(end, record['endAt'])
        observations.append({'startAt': record['startAt'], 'endAt': record['endAt'],
                             'exerciseType': record['exerciseType'], 'exerciseTypeLabel': exercise_type_label(record['exerciseType']),
                             'recordingMethod': record['recordingMethod'],
                             'origin': record['origin'], 'device': record.get('device'),
                             'observedHeartRateSampleCount': sum(record['startAt'] <= p['time'] < record['endAt'] for p in view['heartRate']),
                             'candidateExcursionOverlapCount': sum(record['startAt'] < event['endAt'] and record['endAt'] > event['riseStartAt']
                                                                    for event in (excursions or {}).get('events', [])),
                             'glucoseBefore30m': window(max(start, a-30*MINUTE), a),
                             'glucoseDuring': window(a, b),
                             'glucoseAfter60m': window(b, min(end, b+60*MINUTE))})
    # HR remains descriptive of available samples, not intensity or a continuous coverage estimate.
    return {'source': SOURCE, 'origin': ORIGIN, 'originApp': view['originApp'], 'periodStart': start, 'periodEnd': end,
            'availability': {k: view[k] for k in ('status', 'readableKinds', 'stale', 'lastSyncedAt',
                                                'lastSuccessfulSyncAt', 'sourceWindowStart', 'sourceWindowEnd')},
            'queryCoverageMinutes': view['queryCoverageMinutes'], 'queryCoverageMeaning': view['queryCoverageMeaning'],
            'summary': view['summary'], 'recordedSessions': observations,
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
