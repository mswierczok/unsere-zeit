import base64
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import iu_import
from scripts.build_snapshot import make_snapshot

TZ = ZoneInfo("Europe/Berlin")
SAMPLE = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
    "UID:iu-demo\r\nDTSTART;TZID=Europe/Berlin:20261120T090000\r\n"
    "DTEND;TZID=Europe/Berlin:20261120T121500\r\n"
    "SUMMARY:Studium\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
)


class IUImportTests(unittest.TestCase):
    def test_encrypted_import_roundtrip_and_reject_wrong_key(self):
        key = bytes(range(32))
        nonce = bytes(range(12))
        cipher = AESGCM(key).encrypt(nonce, SAMPLE.encode(), iu_import.AAD)
        payload = dict(v=1, alg="AES-256-GCM", nonce=base64.b64encode(nonce).decode(),
                       ciphertext=base64.b64encode(cipher).decode())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "iu.enc.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(iu_import.load_iu_ics(key.hex(), path), SAMPLE)
            with self.assertRaises(iu_import.IUImportError):
                iu_import.load_iu_ics("ff" * 32, path)

    def test_invalid_import_key(self):
        with self.assertRaises(iu_import.IUImportError):
            iu_import.load_iu_ics("not-a-key", "missing.json")

    def test_iu_and_icloud_overlap_is_deduplicated(self):
        def fake_icloud(now=None):
            return SAMPLE, 1
        def fake_myduty(url, now=None):
            return (
                "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:duty-demo\r\n"
                "DTSTART:20261120T060000\r\nDTEND:20261120T140000\r\n"
                "SUMMARY:Fruehdienst\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
            ), 1
        with patch.dict(os.environ, {
            "ICLOUD_APPLE_ID": "dummy@example.invalid",
            "ICLOUD_APP_PASSWORD": "dummy",
            "MYDUTY_SHARE_URL": "https://myduty.io/s/12345",
            "IU_ICS_IMPORT_KEY": "ab" * 32,
        }), patch.object(iu_import, "load_iu_ics", return_value=SAMPLE):
            snapshot = make_snapshot(
                now=dt.datetime(2026, 11, 19, 12, tzinfo=TZ),
                myduty_sync=fake_myduty,
                icloud_sync=fake_icloud,
            )
        self.assertEqual(len(snapshot["events"]), 2)
        self.assertEqual(snapshot["sources"]["me"]["eventCount"], 1)
        self.assertEqual(snapshot["sources"]["me"]["iuCount"], 1)
        self.assertEqual(snapshot["sources"]["me"]["icloudCount"], 1)
        self.assertEqual(snapshot["sources"]["her"]["eventCount"], 1)

if __name__ == "__main__":
    unittest.main()