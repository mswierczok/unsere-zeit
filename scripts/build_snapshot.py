#!/usr/bin/env python3
"""GitHub Actions only: read authorized calendars, encrypt, publish ciphertext.

The repository and the resulting Pages site can be public; calendar secrets and
plaintext calendar data must NEVER be written to repository-tracked paths.
"""
import base64
import datetime as dt
import json
import os
import pathlib
import secrets
import sys
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calendar_ics import parse_ics
import myduty
import icloud

TZ = ZoneInfo('Europe/Berlin')
OUTPUT = ROOT/'site'/'snapshot.enc.json'


def encode_json(obj,passphrase):
    if not isinstance(passphrase,str) or len(passphrase)<24:
        raise ValueError('SYNC_PASSPHRASE muss mindestens 24 Zeichen lang sein.')
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    salt=secrets.token_bytes(16)
    nonce=secrets.token_bytes(12)
    iterations=350000
    key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=iterations).derive(passphrase.encode('utf-8'))
    cipher=AESGCM(key).encrypt(nonce,raw,None)
    return dict(v=1,kdf='PBKDF2-SHA256',iterations=iterations,
                salt=base64.b64encode(salt).decode('ascii'),
                nonce=base64.b64encode(nonce).decode('ascii'),
                ciphertext=base64.b64encode(cipher).decode('ascii'))


def make_snapshot(now=None,myduty_sync=None,icloud_sync=None):
    current=now or dt.datetime.now(TZ)
    start=current.replace(hour=0,minute=0,second=0,microsecond=0)-dt.timedelta(days=35)
    end=start+dt.timedelta(days=250)
    sources={'me':{'configured':False},'her':{'configured':False}}
    all_events=[]
    if bool(os.getenv('ICLOUD_APPLE_ID')) != bool(os.getenv('ICLOUD_APP_PASSWORD')):
        raise ValueError('iCloud: Beide Zugangsdaten erforderlich.')
    if os.getenv('ICLOUD_APPLE_ID'):
        get_icloud=icloud_sync or icloud.synchronize
        raw,_=get_icloud(now=current)
        items=parse_ics(raw,start,end,'me','iCloud')
        all_events.extend(items)
        sources['me']={'configured':True,'name':'iCloud','eventCount':len(items)}
    if os.getenv('MYDUTY_SHARE_URL'):
        get_myduty=myduty_sync or myduty.synchronize
        raw,_=get_myduty(os.environ['MYDUTY_SHARE_URL'],now=current.date())
        items=parse_ics(raw,start,end,'her','MYDUTY')
        all_events.extend(items)
        sources['her']={'configured':True,'name':'MYDUTY','eventCount':len(items)}
    if len(all_events)>12000:
        raise ValueError('Zu viele Kalendereinträge für diesen Zeitraum.')
    clean=[]
    for event in all_events:
        clean.append({
            'owner':event['owner'],
            'title':str(event['title'])[:250],
            'start':event['start'],
            'end':event['end'],
            'allDay':bool(event.get('allDay')),
            'source':event.get('source','Kalender'),
            'isOff':bool(event.get('isOff')),
            'isNight':bool(event.get('isNight')),
        })
    clean.sort(key=lambda e:(e['start'],e['owner'],e['title']))
    return {'format':1,'updatedAt':current.isoformat(),'periodStart':start.isoformat(),'periodEnd':end.isoformat(),'sources':sources,'events':clean}


def main():
    password=os.getenv('SYNC_PASSPHRASE','')
    if not password:
        # Allow first Pages deployment without any secrets; never ship a stale file.
        OUTPUT.unlink(missing_ok=True)
        print('Noch kein SYNC_PASSPHRASE: App ohne Kalenderdaten veröffentlichen.')
        return
    try:
        data=make_snapshot()
        payload=encode_json(data,password)
        OUTPUT.write_text(json.dumps(payload,separators=(',',':'))+'\n',encoding='utf-8')
    except Exception as error:
        # Do not expose network exceptions, private links or event names in Actions logs.
        print('Kalendersynchronisierung fehlgeschlagen. Prüfe Geheimnisse und MYDUTY-Link-Ablauf.',file=sys.stderr)
        raise SystemExit(1) from None
    print('Verschlüsselter Kalender erstellt. Keine privaten Termine im Build-Log.')


if __name__=='__main__':main()
