"""Descriptive candidate excursions, not a validated meal or hormone diagnostic."""
from datetime import datetime, timedelta, timezone
from statistics import median

from .statistics import DAY, MINUTE, NOMINAL_INTERVAL, metrics, round_value


def day_quality(readings, now):
    start = now-DAY
    ordered = sorted((r for r in readings if r['sourceAt'] <= now), key=lambda r: r['sourceAt'])
    summary = metrics(ordered, start, now)
    cursor, longest = start, 0
    for i, row in enumerate(ordered):
        following = ordered[i+1]['sourceAt'] if i+1 < len(ordered) else now
        left, right = max(start, row['sourceAt']), min(now, following, row['sourceAt']+NOMINAL_INTERVAL)
        if right <= left:
            continue
        longest = max(longest, left-cursor)
        cursor = max(cursor, right)
    longest = max(longest, now-cursor)
    span = now-ordered[0]['sourceAt'] if ordered else 0
    fresh = bool(ordered and ordered[-1]['sourceAt'] >= now-10*MINUTE)
    reasons = []
    if span < DAY:
        reasons.append('尚未积累满24小时（目前约%.1f小时）。' % (span/3600000))
    if summary['coveragePercent'] < 95:
        reasons.append('最近24小时覆盖率需至少95%%（目前%.1f%%）。' % summary['coveragePercent'])
    if longest > 15*MINUTE:
        reasons.append('最近24小时存在超过15分钟的缺测。')
    if not fresh:
        reasons.append('请先恢复最新读数同步。')
    return {'ready': not reasons, 'reason': ' '.join(reasons) or '最近24小时数据已就绪。',
            'coveragePercent': summary['coveragePercent'], 'maxGapMinutes': round_value(longest/MINUTE),
            'spanHours': round_value(span/3600000), 'latestFresh': fresh,
            'policy': '产品数据完整性门槛：跨度24h、覆盖95%、最长缺口15min、最新读数10min内；不是医学验证标准'}


def candidate_excursions(readings, start, end):
    points = sorted((r for r in readings if start <= r['sourceAt'] <= end), key=lambda r: r['sourceAt'])
    segments = []
    for row in points:
        if not segments or row['sourceAt']-segments[-1][-1]['sourceAt'] > 10*MINUTE:
            segments.append([])
        segments[-1].append(row)
    events = []
    tz = timezone(timedelta(hours=8))
    clock = lambda at: datetime.fromtimestamp(at/1000, tz).strftime('%m-%d %H:%M')
    for segment in segments:
        i = 3
        while i < len(segment)-2:
            at = segment[i]['sourceAt']
            baseline_rows = [r for r in segment[:i+1] if at-30*MINUTE <= r['sourceAt'] <= at]
            if len(baseline_rows) < 4 or at-baseline_rows[0]['sourceAt'] < 15*MINUTE:
                i += 1; continue
            values = [r['value'] for r in baseline_rows]
            baseline = median(values)
            if max(values)-min(values) > .6 or abs(segment[i]['value']-baseline) > .3:
                i += 1; continue
            # Three consecutive elevated points spanning >=10min reject isolated spikes.
            detection = None
            for k in range(i+1, len(segment)-2):
                if segment[k]['sourceAt']-at > 45*MINUTE:
                    break
                sustained = segment[k:k+3]
                if sustained[-1]['sourceAt']-sustained[0]['sourceAt'] >= 10*MINUTE and min(r['value'] for r in sustained) >= baseline+.8:
                    detection = k+2; break
            if detection is None:
                i += 1; continue
            # Anchor at the last near-baseline point, not the start of the look-ahead search.
            i = max((k for k in range(i, detection+1) if segment[k]['value'] <= baseline+.15), default=i)
            at = segment[i]['sourceAt']
            # A 3-point median locates a sustained peak; daily extrema remain raw.
            smooth = [median([r['value'] for r in segment[max(0,k-1):k+2]]) for k in range(len(segment))]
            peak = max(range(i, detection+1), key=lambda k: smooth[k])
            last, recovered, boundary = detection, False, 'segment_end'
            for j in range(detection+1, len(segment)):
                if segment[j]['sourceAt']-at > 240*MINUTE:
                    boundary = 'four_hour_limit'; break
                last = j
                if smooth[j] > smooth[peak]:
                    peak = j
                if j > peak and j+1 < len(segment) and max(segment[j]['value'], segment[j+1]['value']) <= baseline+.3:
                    last, recovered, boundary = j+1, True, 'returned_near_baseline'; break
            peak_at, last_at = segment[peak]['sourceAt'], segment[last]['sourceAt']
            rise_minutes = (peak_at-at)/MINUTE
            fall_minutes = (last_at-peak_at)/MINUTE
            peak_value = smooth[peak]
            events.append({'riseStartAt': at, 'peakAt': peak_at, 'endAt': last_at,
                           'riseStartLocal': clock(at), 'peakLocal': clock(peak_at), 'endLocal': clock(last_at),
                           'baseline': round_value(baseline), 'sustainedPeak': round_value(peak_value),
                           'riseAmplitude': round_value(peak_value-baseline), 'riseMinutes': round_value(rise_minutes),
                           'riseRatePerMinute': round_value((peak_value-baseline)/rise_minutes, 3) if rise_minutes else None,
                           'observedFallAmplitude': round_value(max(0, peak_value-segment[last]['value'])),
                           'observedFallMinutes': round_value(fall_minutes),
                           'peakToReturnMinutes': round_value(fall_minutes) if recovered else None,
                           'totalToReturnMinutes': round_value((last_at-at)/MINUTE) if recovered else None,
                           'returnedNearBaseline': recovered, 'endReason': boundary,
                           'mealStatus': '未确认；上升起点仅为候选进餐回顾锚点，不是真实进餐时刻'})
            i = max(last+1, i+1)
    return {'events': events[:12], 'truncated': len(events) > 12,
            'method': '描述性启发式v1：前30min稳定中位基线、45min内持续升幅≥0.8；至少3点跨度10min；≤10min连接；3点中位数定位持续峰；回到基线+0.3需2点；最多跟踪4h',
            'limitations': ['仅为候选餐后样波动，可能漏检或误检；检测阈值不是医学正常值或已验证餐检模型。',
                            '时钟仅帮助回顾可能进餐；CGM上升时间不等于实际进餐时间，不倒推精确吃饭时刻。',
                            '未回到基线、跨缺口或窗口边界时，回落/恢复时长为未知，不能当作已恢复。',
                            '不能由这些指标测量胰岛素分泌、β细胞功能、胰岛素抵抗或胰高血糖素水平。']}
