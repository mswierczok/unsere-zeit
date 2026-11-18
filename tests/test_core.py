import datetime as dt
import json
import os
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import myduty
from calendar_ics import parse_ics
from scripts.build_snapshot import encode_json, make_snapshot

TZ = ZoneInfo('Europe/Berlin')


class CoreTests(unittest.TestCase):
    def test_share_url_validation(self):
        self.assertEqual(
            myduty.share_url('https://link.myduty.io/duty-share/123456789'),
            'https://link.myduty.io/duty-share/123456789',
        )
        for value in ('https://example.com/1', 'http://myduty.io/s/123',
                      'https://link.myduty.io/duty-share/123?x=1',
                      'https://link.myduty.io.evil.test/duty-share/123'):
            with self.assertRaises(myduty.ConnectorError):
                myduty.share_url(value)

    def test_myduty_night_shift_and_off_day(self):
        unit = [dict(dutyUnitId=1, title='Nacht', startTime='2100', endTime='0700', isOffDay=False, isVacation=False),
                dict(dutyUnitId=2, title='Frei', startTime='', endTime='', isOffDay=True, isVacation=False)]
        shifts = [dict(dutyUnitId=1, year='2026', month='11', day='18', scheduleId=17),
                  dict(dutyUnitId=2, year='2026', month='11', day='19', scheduleId=18)]
        data = myduty.normalize(shifts, unit)
        self.assertTrue(data[0]['night'])
        self.assertEqual(data[0]['end'].day, 19)
        self.assertTrue(data[1]['off'])
        ics = myduty.as_ics(data)
        parsed = parse_ics(ics, dt.datetime(2026, 11, 1, tzinfo=TZ),
                           dt.datetime(2026, 12, 1, tzinfo=TZ), 'her', 'MYDUTY')
        self.assertEqual(len(parsed), 2)
        self.assertEqual(len([p for p in parsed if p['isNight']]), 1)
        self.assertEqual(len([p for p in parsed if p['isOff']]), 1)

    def test_empty_snapshot_and_encryption(self):
        with patch.dict(os.environ, {'ICLOUD_APPLE_ID': '', 'ICLOUD_APP_PASSWORD': '', 'MYDUTY_SHARE_URL': ''}):
            snap = make_snapshot(now=dt.datetime(2026, 11, 18, 12, 0, tzinfo=TZ))
        self.assertEqual(snap['events'], [])
        self.assertFalse(snap['sources']['me']['configured'])
        self.assertFalse(snap['sources']['her']['configured'])
        result = encode_json(snap, 'A-Strong-Shared-Secret_At-Least-24-Characters')
        self.assertNotIn('periodStart', json.dumps(result))
        self.assertIn('ciphertext', result)
        with self.assertRaises(ValueError):
            encode_json(snap, 'too_short')

    def test_snapshot_with_both_sources(self):
        def fake_icloud(now=None):
            return ('BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:uni\r\n'
                    'DTSTART:20261120T090000\r\nDTEND:20261120T140000\r\n'
                    'SUMMARY:Uni\r\nEND:VEVENT\r\nEND:VCALENDAR', 1)
        def fake_myduty(url, now=None):
            return ('BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:shift\r\n'
                    'DTSTART:20261120T060000\r\nDTEND:20261120T140000\r\n'
                    'SUMMARY:Frühdienst\r\nEND:VEVENT\r\nEND:VCALENDAR', 1)
        env = {'ICLOUD_APPLE_ID': 'example@example.invalid', 'ICLOUD_APP_PASSWORD': 'placeholder',
               'MYDUTY_SHARE_URL': 'https://myduty.io/s/123456789'}
        with patch.dict(os.environ, env):
            snap = make_snapshot(now=dt.datetime(2026, 11, 18, 12, 0, tzinfo=TZ),
                                 icloud_sync=fake_icloud, myduty_sync=fake_myduty)
        self.assertEqual(len(snap['events']), 2)
        self.assertEqual({e['owner'] for e in snap['events']}, {'me', 'her'})
        self.assertTrue(snap['sources']['me']['configured'])
        self.assertTrue(snap['sources']['her']['configured'])


if __name__ == '__main__':
    unittest.main()
