"""Read-only iCloud CalDAV calendar adapter.

Credentials are supplied as hosting environment secrets. No Apple credential is
accepted via the public API or stored in SQLite. CalDAV queries only; never writes.
This adapter intentionally does NOT expose event details outside the private UI.
"""
import datetime as dt
import hashlib
import os
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Berlin')


class ICloudError(ValueError):
    pass


def configured():
    return bool(os.getenv('ICLOUD_APPLE_ID') and os.getenv('ICLOUD_APP_PASSWORD'))


def selected_names():
    raw = os.getenv('ICLOUD_CALENDAR_NAMES', '').strip()
    return {s.strip().casefold() for s in raw.split(',') if s.strip()}


def extract_events(data, namespace):
    """Extract exact VEVENT blocks, changing UIDs to be calendar-scoped."""
    out = []
    inside, lines = False, []
    for line in str(data).replace('\r\n','\n').replace('\r','\n').split('\n'):
        if line.upper() == 'BEGIN:VEVENT':
            inside, lines = True, [line]
        elif line.upper() == 'END:VEVENT' and inside:
            lines.append(line)
            # UID must not collide across separate iCloud calendars.
            item = '\r\n'.join('UID:' + namespace + '-' + x[4:] if x.upper().startswith('UID:') else x
                               for x in lines)
            if 'BEGIN:VEVENT' in item and 'DTSTART' in item:
                out.append(item)
            inside, lines = False, []
        elif inside:
            lines.append(line)
    return out


def synchronize(client_factory=None, now=None):
    if not configured():
        raise ICloudError('iCloud-Zugang auf dem Server nicht eingerichtet.')
    if client_factory is None:
        try:
            from caldav import DAVClient
            client_factory = DAVClient
        except ImportError as exc:
            raise ICloudError('CalDAV-Paket auf dem Server nicht installiert.') from exc
    start_day = (now or dt.datetime.now(TZ)).date()
    start = dt.datetime.combine(start_day.replace(day=1), dt.time(0), TZ) - dt.timedelta(days=40)
    end = dt.datetime.combine(start_day.replace(day=1), dt.time(0), TZ) + dt.timedelta(days=240)
    desired = selected_names()
    try:
        with client_factory(url='https://caldav.icloud.com',
                            username=os.environ['ICLOUD_APPLE_ID'],
                            password=os.environ['ICLOUD_APP_PASSWORD'], timeout=20) as client:
            calendars = client.principal().calendars()
            blocks = []
            found_names = []
            for index, calendar in enumerate(calendars):
                name = str(calendar.name or '').strip()
                if desired and name.casefold() not in desired:
                    continue
                found_names.append(name)
                namespace = hashlib.sha256((str(index)+'|'+name).encode()).hexdigest()[:12]
                entries = calendar.search(start=start, end=end, event=True, expand=False)
                if len(entries) > 3000:
                    raise ICloudError('Der iCloud-Kalender enthält zu viele Einträge.')
                for entry in entries:
                    blocks.extend(extract_events(entry.data, namespace))
                    if len(blocks) > 6000:
                        raise ICloudError('Zu viele iCloud-Ereignisse zurückgegeben.')
            if desired and {x.casefold() for x in found_names} != desired:
                raise ICloudError('Ein gewählter iCloud-Kalender wurde nicht gefunden. Kalendernamen prüfen.')
            if not found_names:
                raise ICloudError('Keine iCloud-Kalender gefunden.')
    except ICloudError:
        raise
    except Exception as exc:
        # Never include exception text; library exceptions can include endpoint and credentials.
        raise ICloudError('iCloud-CalDAV konnte nicht gelesen werden. Zugang und Kalendernamen prüfen.') from exc
    ics = '\r\n'.join(['BEGIN:VCALENDAR', 'VERSION:2.0',
                       'PRODID:-//Unsere Zeit//Private iCloud Import//DE', *blocks,
                       'END:VCALENDAR', ''])
    return ics, len(blocks)
