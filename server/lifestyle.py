"""User-confirmed lifestyle markers. Text is data, never model instructions."""
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone

DAY = 86400000
EVENT_TYPES = ('meal', 'sleep', 'wake', 'exercise', 'note')
IDENTIFIER = re.compile(r'^[A-Za-z0-9_-]{8,80}$')


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('invalid_event')
    return value


def text(value, limit):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and ord(c) not in (9,10) for c in value):
        raise ValueError('invalid_event')
    return value.strip()


def validate_event(payload, now):
    allowed = {'id', 'type', 'at', 'note', 'meal', 'expectedUpdatedAt'}
    if not isinstance(payload, dict) or set(payload)-allowed:
        raise ValueError('invalid_event')
    at = payload.get('at')
    if type(at) is not int or not now-365*DAY <= at <= now+300000 or payload.get('type') not in EVENT_TYPES:
        raise ValueError('invalid_event')
    event = {'id': identifier(payload.get('id')), 'type': payload['type'], 'at': at,
             'note': text(payload.get('note', ''), 1000)}
    if payload.get('meal') is not None:
        meal = payload['meal']
        if event['type'] != 'meal' or not isinstance(meal, dict) or set(meal)-{'foods', 'estimatedKcalMin', 'estimatedKcalMax', 'source'}:
            raise ValueError('invalid_event')
        low, high = meal.get('estimatedKcalMin'), meal.get('estimatedKcalMax')
        if low is not None or high is not None:
            if any(type(x) not in (int, float) or not 0 <= x <= 20000 or not math.isfinite(x) for x in (low, high)) or low > high:
                raise ValueError('invalid_event')
        source = meal.get('source', 'manual')
        if source not in ('manual', 'photo_estimate'):
            raise ValueError('invalid_event')
        event['meal'] = {'foods': text(meal.get('foods', ''), 1000), 'estimatedKcalMin': low,
                         'estimatedKcalMax': high, 'source': source}
    if 'expectedUpdatedAt' in payload and (type(payload['expectedUpdatedAt']) is not int or payload['expectedUpdatedAt'] <= 0):
        raise ValueError('invalid_event')
    return event, payload.get('expectedUpdatedAt')


def canonical(event):
    return json.dumps({k:v for k,v in event.items() if k != 'updatedAt'}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def context(events, start, end):
    selected = [e for e in events if start <= e['at'] <= end]
    # Personal records are retained intact in storage; only model context is bounded.
    prioritized = sorted(selected, key=lambda e:(e['type'] in ('meal', 'sleep', 'wake', 'exercise'), e['at']), reverse=True)[:24]
    rows = []
    tz = timezone(timedelta(hours=8))
    for event in sorted(prioritized, key=lambda e:e['at']):
        row = {'id':event['id'], 'type':event['type'], 'at':event['at'],
               'localTime':datetime.fromtimestamp(event['at']/1000, tz).isoformat(),
               'minutesBeforePeriodEnd':round((end-event['at'])/60000,1),
               'note':event['note'][:80], 'noteTruncated':len(event['note'])>80, 'confirmedByUser':True}
        if 'meal' in event:
            row['meal'] = dict(event['meal'], foods=event['meal']['foods'][:120],foodsTruncated=len(event['meal']['foods'])>120)
        rows.append(row)
    return {'events':rows, 'totalCount':len(selected), 'truncatedCount':len(selected)-len(rows),
            'meaning':'用户确认的近似事件时刻；睡眠需入睡/起床配对，未记录不代表未发生。食物热量范围可为照片估计，经用户确认仍不是精确摄入。'}
