"""ICS parser with RRULE/EXDATE support from the existing Unsere Zeit backend."""
import datetime as dt
from zoneinfo import ZoneInfo
from dateutil import rrule, tz
TZ = ZoneInfo('Europe/Berlin')

def unfold(s):
    lines = s.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    merged = []
    for line in lines:
        if line.startswith((' ', '\t')) and merged:
            merged[-1] += line[1:]
        else:
            merged.append(line)
    return merged


def event_properties(lines):
    props = {}
    for line in lines:
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        parts = key.split(';')
        parameters = {}
        for item in parts[1:]:
            if '=' in item:
                a, b = item.split('=', 1)
                parameters[a.upper()] = b.strip('"')
        props.setdefault(parts[0].upper(), []).append((value, parameters))
    return props


def ical_dt(value, params):
    value = value.strip()
    if params.get('VALUE') == 'DATE' or (len(value) == 8 and value.isdigit()):
        return dt.datetime.strptime(value[:8], '%Y%m%d').replace(tzinfo=TZ)
    if value.endswith('Z'):
        return dt.datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc).astimezone(TZ)
    if len(value) == 15:
        naive = dt.datetime.strptime(value, '%Y%m%dT%H%M%S')
    elif len(value) == 13:
        naive = dt.datetime.strptime(value, '%Y%m%dT%H%M')
    else:
        raise ValueError('Unbekanntes ICS-Datum')
    zone_name = params.get('TZID', 'Europe/Berlin').lstrip('/')
    zone = tz.gettz(zone_name) or TZ
    return naive.replace(tzinfo=zone).astimezone(TZ)


def ical_duration(v):
    import re
    m = re.fullmatch(r'([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?', v)
    if not m:
        return dt.timedelta(hours=1)
    sign = -1 if m.group(1) == '-' else 1
    return sign * dt.timedelta(weeks=int(m.group(2) or 0), days=int(m.group(3) or 0), hours=int(m.group(4) or 0), minutes=int(m.group(5) or 0), seconds=int(m.group(6) or 0))


def parse_ics(content, start, end, owner, source):
    from collections import defaultdict
    all_entries = []
    buf, inside = [], False
    for line in unfold(content):
        if line.upper() == 'BEGIN:VEVENT':
            inside, buf = True, []
        elif line.upper() == 'END:VEVENT' and inside:
            all_entries.append(event_properties(buf))
            inside = False
        elif inside:
            buf.append(line)
    by_uid = defaultdict(list)
    for i, p in enumerate(all_entries):
        by_uid[(p.get('UID') or [(str(i), {})])[0][0]].append(p)
    out = []
    max_occur = 3000

    def to_event(p, begin, duration, uid):
        title = (p.get('SUMMARY') or [('Termin', {})])[0][0]
        title = title.replace('\\n', ' ').replace('\\,', ',').replace('\\;', ';').strip() or 'Termin'
        is_all = bool(p.get('DTSTART') and (p['DTSTART'][0][1].get('VALUE') == 'DATE' or len(p['DTSTART'][0][0]) == 8)) or (p.get('X-UNSERE-ZEIT-ALLDAY') or [('FALSE', {})])[0][0].upper() == 'TRUE'
        is_off = (p.get('X-UNSERE-ZEIT-OFF') or [('FALSE', {})])[0][0].upper() == 'TRUE'
        is_night = (p.get('X-UNSERE-ZEIT-NIGHT') or [('FALSE', {})])[0][0].upper() == 'TRUE'
        if p.get('TRANSP', [('OPAQUE', {})])[0][0].upper() == 'TRANSPARENT':
            return None
        if p.get('STATUS', [('', {})])[0][0].upper() == 'CANCELLED':
            return None
        finish = begin + duration
        if finish <= start or begin >= end:
            return None
        return dict(owner=owner, title=title, start=begin.isoformat(), end=finish.isoformat(), allDay=is_all, source=source, uid=uid, isOff=is_off, isNight=is_night)

    for uid, entries in by_uid.items():
        masters = [p for p in entries if 'RECURRENCE-ID' not in p]
        exceptions = [p for p in entries if 'RECURRENCE-ID' in p]
        excluded = set()
        for p in exceptions:
            try:
                excluded.add(ical_dt(*p['RECURRENCE-ID'][0]).isoformat())
            except (KeyError, ValueError):
                continue
            if 'DTSTART' not in p:
                continue
            try:
                b = ical_dt(*p['DTSTART'][0])
                if 'DTEND' in p:
                    d = ical_dt(*p['DTEND'][0]) - b
                elif 'DURATION' in p:
                    d = ical_duration(p['DURATION'][0][0])
                else:
                    d = dt.timedelta(days=1 if len(p['DTSTART'][0][0]) == 8 else 0, hours=0 if len(p['DTSTART'][0][0]) == 8 else 1)
                obj = to_event(p, b, d, uid)
                if obj:
                    out.append(obj)
            except ValueError:
                pass
        for p in masters:
            if 'DTSTART' not in p:
                continue
            try:
                base = ical_dt(*p['DTSTART'][0])
                if 'DTEND' in p:
                    duration = ical_dt(*p['DTEND'][0]) - base
                elif 'DURATION' in p:
                    duration = ical_duration(p['DURATION'][0][0])
                else:
                    all_day = p['DTSTART'][0][1].get('VALUE') == 'DATE' or len(p['DTSTART'][0][0]) == 8
                    duration = dt.timedelta(days=1) if all_day else dt.timedelta(hours=1)
                duration = max(dt.timedelta(minutes=1), duration)
                begin_window = start - duration
                occurrences = []
                if 'RRULE' in p:
                    rule = rrule.rrulestr(p['RRULE'][0][0], dtstart=base)
                    occurrences.extend(rule.between(begin_window, end, inc=True)[:max_occur])
                else:
                    occurrences.append(base)
                for val, par in p.get('RDATE', []):
                    for token in val.split(','):
                        try:
                            occurrences.append(ical_dt(token, par))
                        except ValueError:
                            pass
                for val, par in p.get('EXDATE', []):
                    for token in val.split(','):
                        try:
                            excluded.add(ical_dt(token, par).isoformat())
                        except ValueError:
                            pass
                seen = set()
                for occurrence in occurrences[:max_occur]:
                    b = occurrence.astimezone(TZ)
                    key = b.isoformat()
                    if key in excluded or key in seen:
                        continue
                    seen.add(key)
                    obj = to_event(p, b, duration, uid)
                    if obj:
                        out.append(obj)
            except (ValueError, OverflowError, TypeError):
                continue
    return out


