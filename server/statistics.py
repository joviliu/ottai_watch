"""Time-weighted CGM observations; no interpolation or clinical target inference."""
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone as fixed_timezone
from statistics import median

MINUTE = 60_000
DAY = 1440 * MINUTE
NOMINAL_INTERVAL = 5 * MINUTE


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    left = math.floor(position)
    right = math.ceil(position)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def round_value(value, digits=2):
    return None if value is None else round(value, digits)


def metrics(readings, start, end):
    if end <= start:
        raise ValueError('Invalid observation window')
    segments = []
    for i, reading in enumerate(readings):
        at = reading['sourceAt']
        following = readings[i + 1]['sourceAt'] if i + 1 < len(readings) else end
        # A CGM sample receives at most one nominal five-minute interval of weight.
        # Long gaps remain missing, and dense packets cannot double-count a minute.
        left = max(start, at)
        right = min(end, following, at + NOMINAL_INTERVAL)
        if right > left:
            segments.append((reading['value'], right - left))
    total = sum(weight for _, weight in segments)
    samples = [r for r in readings if start <= r['sourceAt'] < end]
    mean = sum(value * weight for value, weight in segments) / total if total else None
    sd = math.sqrt(sum(weight * (value - mean)**2 for value, weight in segments) / total) if total else None
    def percentage(condition):
        return round_value(100 * sum(w for v, w in segments if condition(v)) / total) if total else None
    limits = []
    coverage = 100 * total / (end - start)
    if coverage < 70:
        limits.append('该时段数据覆盖不足70%；缺测可能使均值、极值和范围占比偏倚，不能视作全天代表性。')
    if not segments:
        limits.append('该时段无可用读数。')
    return {
        'periodStart': start, 'periodEnd': end, 'unit': 'mmol/L',
        'sampleCount': len(samples), 'observedMinutes': round_value(total / MINUTE),
        'expectedMinutes': round_value((end - start) / MINUTE), 'coveragePercent': round_value(coverage),
        'mean': round_value(mean), 'sd': round_value(sd),
        'cvPercent': round_value(100 * sd / mean) if mean else None,
        'min': min((v for v, _ in segments), default=None), 'max': max((v for v, _ in segments), default=None),
        'range': {'low': 3.9, 'high': 7.8, 'label': '用户观察范围；非个体化医学目标'},
        'inRangePercent': percentage(lambda v: 3.9 <= v <= 7.8),
        'belowRangePercent': percentage(lambda v: v < 3.9),
        'aboveRangePercent': percentage(lambda v: v > 7.8),
        'below3Percent': percentage(lambda v: v < 3.0),
        'above13_9Percent': percentage(lambda v: v > 13.9),
        'diabetesReferenceInRangePercent': percentage(lambda v: 3.9 <= v <= 10.0),
        'diabetesReferenceLabel': '3.9–10.0；仅糖尿病人群CGM共识参考，不作为本用户诊断或达标目标',
        'limitations': limits,
    }


def historical_profile(readings, start, end, timezone='Asia/Shanghai'):
    if timezone != 'Asia/Shanghai':
        raise ValueError('Only Asia/Shanghai observation timezone is configured')
    tz = fixed_timezone(timedelta(hours=8))
    daily = defaultdict(lambda: defaultdict(list))
    for reading in readings:
        if not start <= reading['sourceAt'] < end:
            continue
        at = datetime.fromtimestamp(reading['sourceAt'] / 1000, tz)
        bucket = (at.hour * 60 + at.minute) // 30 * 30
        daily[bucket][at.date().isoformat()].append(reading['value'])
    points = []
    days = set()
    for minute, buckets in sorted(daily.items()):
        values = [median(points) for points in buckets.values()]
        days.update(buckets)
        points.append({'minuteOfDay': minute, 'median': round_value(median(values)),
                       'p25': round_value(percentile(values, .25)), 'p75': round_value(percentile(values, .75)),
                       'sampleDays': len(values)})
    return {'basis': 'previous_28_days_excluding_latest_24h', 'timezone': timezone,
            'periodStart': start, 'periodEnd': end, 'daysAvailable': len(days), 'points': points}


def analysis_input(readings, now, timezone='Asia/Shanghai'):
    windows = {}
    for key, start, end in [('latest24h', now-DAY, now), ('previous24h', now-2*DAY, now-DAY),
                            ('latest7d', now-7*DAY, now), ('previous7d', now-14*DAY, now-7*DAY),
                            ('latest14d', now-14*DAY, now), ('previous14d', now-28*DAY, now-14*DAY),
                            ('previous28d', now-56*DAY, now-28*DAY)]:
        windows[key] = metrics(readings, start, end)
    # Far history is summarized per day, preserving sample coverage; raw rows remain in SQLite.
    daily = []
    for offset in range(56, 0, -1):
        start, end = now-offset*DAY, now-(offset-1)*DAY
        item = metrics(readings, start, end)
        if item['sampleCount']:
            daily.append(dict({'daysBeforeCurrent': offset}, **{key: item[key] for key in (
                'sampleCount', 'coveragePercent', 'mean', 'min', 'max', 'sd', 'cvPercent',
                'inRangePercent', 'belowRangePercent', 'aboveRangePercent', 'below3Percent', 'above13_9Percent')}))
    older = []
    for newer in range(56, 365, 28):
        older_boundary = min(newer+28, 365)
        item = metrics(readings, now-older_boundary*DAY, now-newer*DAY)
        if item['sampleCount']:
            older.append(dict({'periodStartDaysBeforeCurrent': older_boundary,
                               'periodEndDaysBeforeCurrent': newer,
                               'windowDays': older_boundary-newer}, **{key: item[key] for key in (
                'sampleCount', 'observedMinutes', 'expectedMinutes', 'coveragePercent', 'mean', 'min', 'max',
                'sd', 'cvPercent', 'inRangePercent', 'belowRangePercent', 'aboveRangePercent',
                'below3Percent', 'above13_9Percent')}))
    recent_quality = metrics(readings, now-3*DAY, now)
    actual_times = [r['sourceAt'] for r in readings if now-365*DAY <= r['sourceAt'] <= now]
    history_status = {
        'sourceSpanHours': round((max(actual_times)-min(actual_times))/3600000, 1) if actual_times else 0,
        'totalSampleCountWithin365d': len(actual_times),
        'observedMinutesLast72h': recent_quality['observedMinutes'],
        'coveragePercentLast72h': recent_quality['coveragePercent'],
        'note': '时间跨度不等于连续记录时长或完整天数；即使跨过3天，也须按实际覆盖和采样数判断资料是否充分。',
    }
    comparisons = []
    for newer, prior in [('latest24h', 'previous24h'), ('latest7d', 'previous7d'), ('latest14d', 'previous14d')]:
        recent, baseline = windows[newer], windows[prior]
        notes = []
        if not recent['sampleCount'] or not baseline['sampleCount']:
            notes.append('至少一个窗口没有观测点，无法比较。')
        if recent['coveragePercent'] < 100 or baseline['coveragePercent'] < 100:
            notes.append('存在缺测；比较须同时报告两个窗口的覆盖率，不能假定缺测部分正常。')
        comparisons.append({'recentWindow': newer, 'baselineWindow': prior,
                            'bothHaveObservations': bool(recent['sampleCount'] and baseline['sampleCount']),
                            'recentCoveragePercent': recent['coveragePercent'],
                            'baselineCoveragePercent': baseline['coveragePercent'], 'limitations': notes})
    personal_baselines = []
    for name, low, high in [('此前7天', 2, 8), ('较早第15–28天', 15, 28)]:
        days = [r for r in daily if low <= r['daysBeforeCurrent'] <= high and r['coveragePercent'] >= 95]
        values = {}
        if len(days) >= 3:
            for field in ['mean','sd','cvPercent','min','max','inRangePercent','aboveRangePercent','belowRangePercent']:
                reference = median([d[field] for d in days if d[field] is not None])
                current = windows['latest24h'][field]
                values[field] = {'dailyMedian': round_value(reference), 'currentMinusReference': round_value(current-reference) if current is not None else None}
        personal_baselines.append({'label':name,'eligibleDays':len(days),'minimumDays':3,'coverageRequired':95,
                                   'comparable':len(days)>=3 and windows['latest24h']['coveragePercent']>=95,
                                   'metrics':values,'meaning':'自身完整日指标的日间中位数；不是医学正常值，不能据差值单独归因饮食或激素变化'})
    return {
        'schemaVersion': 1, 'timezone': timezone,
        'profile': '成人非诊断性观察模式；不预设糖尿病或糖前期诊断；未提供用药/饮食/活动记录，不能据CGM诊断',
        'rangeMeaning': '3.9–7.8仅为用户观察范围；3.9–10仅糖尿病人群共识参考；不输出GMI或推算HbA1c诊断',
        'personalBaselines': personal_baselines,
        'healthyReference': {'source': 'Shah et al. 2019 / doi:10.1210/jc.2018-02763',
                             'researchCohortMeanMmolL': 5.5, 'researchWithinPersonCVMeanPercent': 17,
                             'researchRange39To78MedianPercent': 96, 'researchRange39To78IQRPercent': [93,98],
                             'referenceOnly': True, 'populationNote': '健康非糖尿病研究样本，含不同年龄段；Dexcom G6，非个人同龄同餐匹配标准，不能把均值/CV/96%设为个人目标', 'meaning': '健康人群CGM研究提供描述性参考，不存在可直接套用到本人的单条理想餐后曲线；须考虑餐食、活动、年龄与传感器差异'},
        'windows': windows, 'dailySummaries': daily, 'older28DaySummaries': list(reversed(older)),
        'historyStatus': history_status, 'comparisonAvailability': comparisons,
        'recentReadingColumns': ['minutesBeforeCurrent', 'mmolPerL'],
        'recentReadings': [[round((now-r['sourceAt'])/MINUTE, 1), r['value']]
                           for r in readings if now-DAY <= r['sourceAt'] <= now],
        'historicalTimeOfDay': historical_profile(readings, now-29*DAY, now-DAY, timezone),
        'method': '每点最多5分钟向前权重；不插值、不平滑计算指标；时段缺口保持缺测；历史日内每30分钟先日内中位数、再跨日中位数和四分位区间；不是诊断或治疗建议',
    }
