# Unsere Zeit – kostenloser gemeinsamer iPhone-Kalender

Eine eigenständige, für iPhones optimierte Web-App (PWA) auf **GitHub Pages**. Sie zeigt die eigenen iCloud-Termine und die MYDUTY-Dienstschichten zusammen an und berechnet **mögliche** gemeinsame Zeitfenster. GitHub Actions ruft die autorisierten Kalender regelmäßig ab, verschlüsselt einen Kalender-Snapshot und veröffentlicht **nur die verschlüsselte Datei**.

> **Wichtig:** Das GitHub-Pages-Projekt ist eine **öffentlich erreichbare Website**, keine Seite mit serverseitigem Login. Kalenderdaten werden mit einem starken gemeinsamen Passwort **im Browser entschlüsselt**. Wer die URL kennt, kann die verschlüsselte Datei herunterladen. Diese Konstruktion ist nur so privat wie der gemeinsame Schlüssel und die verwendete Verschlüsselung. Keine Zugangsdaten in GitHub-Dateien schreiben!

## Status

- ✅ Statische iPhone-Web-App mit Homescreen-Icon, Monatsübersicht, Tagesdetails, gemeinsamer Freizeit und einstellbarer Erholungszeit nach Nachtdiensten
- ✅ Ein verschlüsselter Kalender-Snapshot (AES-GCM mit PBKDF2-SHA256) statt ungeschützter Kalenderdateien
- ✅ GitHub-Actions-Workflow für einen **ungefähr** stündlichen Datenabruf
- ✅ iCloud CalDAV (nur lesen) und inoffizieller MYDUTY-Freigabelink-Adapter vorhanden
- ⚠️ Echte iCloud-/MYDUTY-Verbindungen können erst nach Einrichtung der Geheimnisse in GitHub geprüft werden
- ⚠️ MYDUTY-Freigabelinks laufen ab und müssen dann aktualisiert werden; eine automatische Erneuerung wird nicht behauptet
- ⚠️ Geplante GitHub Actions können verzögert oder übersprungen werden und werden bei **60 Tagen ohne Repository-Aktivität** in öffentlichen Repos automatisch deaktiviert
- ⚠️ GitHub Pages erlaubt kein sicheres interaktives Zurückschreiben neuer Termine in die Quellkalender. Die Web-App ist nur lesend.

## 1. GitHub-Repository anlegen (einmalig)

GitHub → **New repository**: `unsere-zeit`, Sichtbarkeit **Public**, „Add a README file“ **aktivieren**, dann **Create repository**.

Der Assistent kann die weiteren Dateien über die verbundene GitHub-App hochladen, sobald das Repository angelegt ist. *Die Repository-Erstellung selbst ist mit der verfügbaren Verbindung nicht möglich.* Alternativ können die Dateien aus diesem ZIP in das Repository hochgeladen werden. Der bestehende `carpet-grand-prix`-Code darf dabei unverändert bleiben.

## 2. Dateien hochladen

Alle Dateien samt Ordnern aus diesem Projekt in das neue Repository hochladen, insbesondere `.github/workflows/pages.yml`, `scripts/`, `site/`, `icloud.py`, `myduty.py`, `calendar_ics.py` und `requirements.txt`. **Nicht nur die ZIP-Datei** hochladen; sie muss entpackt sein. GitHub hat in **Add file → Upload files** eine Uploadfunktion für Dateien und Ordner.

Keine `.env`, Kalenderexporte, iCloud-Passwörter oder MYDUTY-Links einchecken.

## 3. Pages einschalten

Im neuen Repository **Settings → Pages → Build and deployment → Source → GitHub Actions** wählen. Wenn „Settings“ nicht angezeigt wird, prüfen, dass du im richtigen Repository angemeldet bist. In **Actions** kannst du den Workflow `Unsere Zeit – Kalender aktualisieren und Pages veröffentlichen` manuell mit **Run workflow** starten. Beim ersten Start ohne Geheimnisse wird **nur die App** ohne Kalenderdaten veröffentlicht. In diesem Zustand kannst du über „Demo ansehen“ die Oberfläche mit erfundenen Terminen testen.

Die Adresse wird bei erfolgreicher Veröffentlichung unter **Settings → Pages** angezeigt. Für den GitHub-Account `mswierczok` und den Repositorynamen `unsere-zeit` wäre das übliche Adressmuster `https://mswierczok.github.io/unsere-zeit/` – erst nach dem tatsächlichen Deployment verwenden.

## 4. Kalender sicher anschließen

**Nie Passwörter oder den MYDUTY-Link im Chat oder in einer GitHub-Datei speichern.** Nutze ausschließlich **Settings → Secrets and variables → Actions → New repository secret**.

| Name des Secrets | Wert (nur direkt bei GitHub eintragen) |
|---|---|
| `SYNC_PASSPHRASE` | Ein selbst generierter, **starker gemeinsamer Schlüssel** von mindestens 24 Zeichen, den ihr sicher im Passwortmanager speichert und beide in der Web-App eingebt. |
| `ICLOUD_APPLE_ID` | E-Mail-Adresse des für die Kalender verwendeten Apple-Accounts. |
| `ICLOUD_APP_PASSWORD` | Ein **neu generiertes anwendungsspezifisches Apple-Passwort** für Kalenderzugriff (nicht dein normales Apple-Passwort). Erstellen bei https://account.apple.com/ → Anmeldung & Sicherheit → App-spezifische Passwörter. |
| `MYDUTY_SHARE_URL` | Der aktuelle Freigabelink aus MYDUTY deiner Freundin; bei Ablauf hier ersetzen. |

Die zu lesenden iCloud-Kalender sind im Workflow derzeit auf `Arbeit,Studium,Privat` eingestellt. Sie dürfen leer sein. Falls ihr später weitere Kalender braucht, `ICLOUD_CALENDAR_NAMES` in `.github/workflows/pages.yml` anpassen.

**Dann:** Actions → Workflow → **Run workflow**. Im **Actions**-Protokoll auf Erfolg achten; die App zeigt den Zeitstempel des letzten erfolgreichen Snapshots an. Ein fehlgeschlagener Abruf lässt die vorherige Version der veröffentlichten Website unverändert (alte Daten bleiben dann vorerst sichtbar).

## 5. App auf den beiden iPhones installieren

Die GitHub-Pages-Adresse mit **Safari** öffnen → **Teilen** → **Zum Home-Bildschirm** → **Hinzufügen**. Auf beiden iPhones den **gleichen starken Schlüssel** beim Öffnen eingeben. Der Schlüssel wird **nicht dauerhaft auf dem Gerät gespeichert**, sondern nur im Arbeitsspeicher solange die App geöffnet ist.

## 6. Pflege und realistische Grenzen

- **iCloud:** Solange das Apple-App-Passwort gültig ist und die Kalender lesbar sind, wird ungefähr stündlich abgerufen. Das ChatGPT-iCloud-Plugin ist dabei **nicht** der dauerhafte Sync-Zugang; hierfür dient CalDAV.
- **MYDUTY:** Der Freigabelink wird innerhalb seiner Gültigkeit neu abgerufen. Danach einen neuen Link erstellen und nur das Secret `MYDUTY_SHARE_URL` ersetzen. Der Adapter ist inoffiziell und kann bei Änderungen der MYDUTY-Webseite ausfallen.
- **Gemeinsam frei:** Die App errechnet *mögliche* Zeitfenster von 09:00–21:00 und kann keine ungeteilten Verpflichtungen, Wegezeiten oder unerfasste Termine berücksichtigen. Bei unvollständiger oder alter Synchronisierung erscheint eine deutliche Warnung.
- **GitHub Actions:** Zeitpläne laufen nur nach bestem Bemühen. In einem öffentlichen Repo werden geplante Workflows nach 60 Tagen ohne Repository-Aktivität deaktiviert. Dann müssen sie in Actions wieder aktiviert werden. Prüft regelmäßig den `Zuletzt synchronisiert`-Status.
- **Datenschutz:** Die URL ist öffentlich, die Kalendersnapshot-Datei verschlüsselt. Ihr habt kein individuelles Benutzerkonto; ein gemeinsamer Schlüssel steuert den Zugang. Für besonders sensible Details ist ein privater Server besser.
- **Kosten:** GitHub Pages und die regulären GitHub-hosted-Action-Läufe auf einem öffentlichen Repository sind nach den derzeitigen Bedingungen kostenlos. Plattformbedingungen können sich ändern.

## Technischer Aufbau

```
MYDUTY-Freigabelink ──┐
                     ├── GitHub Actions (Secrets) ── AES-GCM ── GitHub Pages
Apple iCloud CalDAV ┘                                         │
                                                 iPhone 1 / iPhone 2
                                             Entschlüsselung im Browser
```

Der Build erzeugt die temporäre Datei `site/snapshot.enc.json` **nur im Actions-Runner**. Sie steht auf `.gitignore`, wird also nicht in das Git-Repository committed. **Der veröffentlichte Snapshot ist jedoch öffentlich abrufbar** – nur in verschlüsselter Form.

## Entwicklung / Tests

Python 3.12+, `pip install -r requirements.txt`, dann `python -m unittest discover -s tests -v`. JavaScript-Syntax mit `node --check site/app.js` prüfbar. Eine echte Live-Synchronisierung kann nur mit den jeweiligen autorisierten Zugangsdaten in Actions getestet werden.
