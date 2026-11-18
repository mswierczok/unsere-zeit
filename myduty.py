"""MYDUTY share-link adapter for the *user-authorized* public share view.

Unofficial. Does not use credentials, bypass expiry or access private APIs.
Data format established from the public MyDuty Connector repo (hexdrinker).
"""
import datetime as dt
import html.parser
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Berlin')
SHARE_RE = re.compile(r'^https://(myduty\.io/s|link\.myduty\.io/duty-share)/(\d+)/?$', re.I)
MAX_RESPONSE = 2_000_000
BROWSER_AGENT = 'Mozilla/5.0 (compatible; UnsereZeitCalendar/1.0; +https://myduty.io)' 


class ConnectorError(ValueError):
    """Safe diagnostic shown in the application (never includes the share token)."""


def share_url(raw):
    """Strict canonical allowlist prevents arbitrary URL/SSRF through the connector."""
    if not isinstance(raw, str):
        raise ConnectorError('Bitte einen MYDUTY-Freigabelink eingeben.')
    match = SHARE_RE.fullmatch(raw.strip())
    if not match:
        raise ConnectorError('MYDUTY-Link nicht erkannt (myduty.io/s/… oder link.myduty.io/duty-share/…).')
    return 'https://' + match.group(1).lower() + '/' + match.group(2)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConnectorError('MYDUTY hat auf eine andere Adresse weitergeleitet; bitte den Freigabelink prüfen.')


def fetch(url, data=None, headers=None):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in ('myduty.io', 'link.myduty.io') or parts.port not in (None, 443):
        raise ConnectorError('Abruf außerhalb der MYDUTY-Domain ist nicht erlaubt.')
    # Defence in depth; DNS should only resolve to publicly routable IP addresses.
    try:
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ConnectorError('MYDUTY-Host konnte nicht sicher erreicht werden.')
    except socket.gaierror as exc:
        raise ConnectorError('MYDUTY-Host derzeit nicht erreichbar.') from exc
    req = urllib.request.Request(url, data=data, headers=headers or {}, method='POST' if data is not None else 'GET')
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=12) as resp:
            body = resp.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise ConnectorError('MYDUTY-Antwort überschreitet 2 MB.')
            return body.decode('utf-8-sig')
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404, 410):
            raise ConnectorError('MYDUTY-Link ist abgelaufen oder nicht mehr freigegeben. Neuen Link einsetzen.') from exc
        raise ConnectorError(f'MYDUTY antwortet mit HTTP {exc.code}.') from exc
    except urllib.error.URLError as exc:
        raise ConnectorError('Verbindung zu MYDUTY derzeit nicht möglich.') from exc


class ScriptParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.buf = []
    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == '__myduty_bootstrap__':
            self.active = True
    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.active = False
    def handle_data(self, data):
        if self.active:
            self.buf.append(data)


def parse_bootstrap(markup):
    parser = ScriptParser()
    parser.feed(markup)
    data = ''.join(parser.buf).strip()
    if not data:
        raise ConnectorError('MYDUTY-Datenformat nicht erkannt; Webseite könnte sich geändert haben.')
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ConnectorError('MYDUTY lieferte kein gültiges Schichtformat.') from exc
    if not isinstance(obj, dict) or not str(obj.get('userId', '')).isdigit() or not isinstance(obj.get('dutyUnits'), list):
        raise ConnectorError('MYDUTY lieferte ein unbekanntes Schichtformat.')
    return str(obj['userId']), obj['dutyUnits']


def hhmm(value):
    value = str(value or '')
    if not re.fullmatch(r'\d{4}', value):
        return None
    try:
        return dt.time(int(value[:2]), int(value[2:]))
    except ValueError:
        return None


def normalize(shifts, units):
    by_id = {str(u.get('dutyUnitId')): u for u in units if isinstance(u, dict)}
    events = []
    for row in shifts:
        if not isinstance(row, dict):
            continue
        unit = by_id.get(str(row.get('dutyUnitId')))
        if not unit:
            continue
        try:
            day = dt.date(int(row['year']), int(row['month']), int(row['day']))
        except (ValueError, KeyError, TypeError):
            continue
        title = str(unit.get('title') or 'Dienst')[:60]
        off = bool(unit.get('isOffDay') or unit.get('isVacation'))
        starts, ends = hhmm(unit.get('startTime')), hhmm(unit.get('endTime'))
        whole_day = bool(unit.get('isWholeDay')) or starts is None or ends is None or starts == ends
        if whole_day:
            beginning = dt.datetime.combine(day, dt.time(0), TZ)
            finish = beginning + dt.timedelta(days=1)
        else:
            beginning = dt.datetime.combine(day, starts, TZ)
            finish = dt.datetime.combine(day, ends, TZ)
            if finish <= beginning:
                finish += dt.timedelta(days=1)
        events.append({'date': day.isoformat(), 'title': title, 'start': beginning, 'end': finish,
                       'off': off, 'all_day': whole_day, 'night': (not whole_day and finish.date() > beginning.date() and starts.hour >= 18) or bool(re.search(r'^(?:N|ND|Night|Nacht)', title, re.I)), 'unit': str(row['dutyUnitId']),
                       'schedule': str(row.get('scheduleId', ''))})
    return events


def ics_escape(value):
    return str(value).replace('\\', '\\\\').replace('\n', ' ').replace(',', '\\,').replace(';', '\\;')


def as_ics(events):
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Unsere Zeit//MYDUTY Adapter//DE', 'X-WR-CALNAME:MYDUTY']
    for item in sorted(events, key=lambda x: (x['start'], x['title'])):
        lines.extend([
            'BEGIN:VEVENT',
            f"UID:myduty-{item['date']}-{item['unit']}-{item['schedule']}@unsere-zeit.local",
            'DTSTAMP:20260101T000000Z',
            'DTSTART;TZID=Europe/Berlin:' + item['start'].strftime('%Y%m%dT%H%M%S'),
            'DTEND;TZID=Europe/Berlin:' + item['end'].strftime('%Y%m%dT%H%M%S'),
            'SUMMARY:' + ics_escape(item['title']),
            'X-UNSERE-ZEIT-OFF:' + ('TRUE' if item['off'] else 'FALSE'),
            'X-UNSERE-ZEIT-NIGHT:' + ('TRUE' if item['night'] else 'FALSE'),
            'X-UNSERE-ZEIT-ALLDAY:' + ('TRUE' if item['all_day'] else 'FALSE'),
            'END:VEVENT',
        ])
    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines) + '\r\n'


def month_window(now=None):
    today = now or dt.datetime.now(TZ).date()
    # Previous month and the current + next 3 (five months total).
    months = []
    for delta in range(-1, 4):
        serial = today.year * 12 + today.month - 1 + delta
        year, month0 = divmod(serial, 12)
        months.append((year, month0 + 1))
    return months


def synchronize(raw_url, now=None, fetcher=fetch):
    """Fetch a share view and monthly schedules, returning ICS + number of events.

    Network fetch calls use only owner-shared links and the same share host. We do not
    attempt to automatically renew expired tokens or use any MYDUTY credentials.
    """
    url = share_url(raw_url)
    origin = urllib.parse.urlsplit(url).scheme + '://' + urllib.parse.urlsplit(url).hostname
    # Allow tests to pass a mock fetcher (no real calendar or account needed).
    content = fetcher(url, None, {'User-Agent': BROWSER_AGENT})
    user_id, units = parse_bootstrap(content)
    all_events = []
    for year, month in month_window(now):
        form = urllib.parse.urlencode({'userId': user_id, 'yyyy': str(year), 'mm': f'{month:02d}', 'mode': 'production'}).encode()
        payload = json.loads(fetcher(origin + '/proxy/getUserDutySchedules', form, {
            'Content-Type': 'application/x-www-form-urlencoded', 'Referer': url, 'Origin': origin,
            'User-Agent': BROWSER_AGENT,
        }))
        if not isinstance(payload, dict) or payload.get('header', {}).get('status') != 'success':
            raise ConnectorError(f'MYDUTY konnte den Dienstplan {month:02d}/{year} nicht liefern.')
        try:
            shifts = payload['body']['schedules']['duty']
        except (KeyError, TypeError) as exc:
            raise ConnectorError('MYDUTY-Datenformat hat sich geändert.') from exc
        if not isinstance(shifts, list):
            raise ConnectorError('MYDUTY-Schichtliste nicht erkannt.')
        all_events.extend(normalize(shifts, units))
    return as_ics(all_events), len(all_events)
