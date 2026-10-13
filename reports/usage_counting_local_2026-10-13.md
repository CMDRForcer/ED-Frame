# Aktive Installationen: lokaler Stand vom 13.10.2026

Implementiert sind ausschließlich Installationszählungen. Die App sendet eine
zufällige UUID4 und APP_VERSION, mit User-Agent ED-Frame/APP_VERSION und
5-Sekunden-Request-Timeout. Kein Commander, FID, Journal, Hardwaremerkmal,
Spielereignis oder Bildschirm-/Aktivitätsdatensatz wird übertragen.

Die gemeinsame Datei `%LOCALAPPDATA%/ED-Frame/usage_ping.json` liegt außerhalb
der Commander-Profile. Sie enthält nur ID und Tagesmarker. Die ID
entsteht beim ersten zulässigen Ping oder beim Öffnen von About. Der vor dem
HTTP-Aufruf gespeicherte Versuchsmarker begrenzt auch nach Fehlern und Neustarts
auf einen Versuch pro UTC-Tag; versäumte Tage werden nicht nachgesendet.
Erfolgreiche Pings erhalten zusätzlich ihren erfolgreichen Tagesmarker.

Ein vorhandener Hintergrund-Worker übernimmt den Request. Beim Start wird nach
zehn Sekunden geprüft, danach alle 30 Minuten; diese Prüfungen sind keine
wiederholten HTTP-Abrufe. Dev-Build, EDFRAME_NO_USAGE_PING=1 oder abgeschalteter
Katalog verhindern Pings. Fehler gehen nur mit einer generischen Meldung ins
lokale Log. Auf deinen Wunsch läuft die Zählung in Release-Builds automatisch;
einen eigenen Schalter gibt es weder in Connections noch im Onboarding. Beide
Bereiche erklären die übermittelten Daten. Ein früheres lokales `enabled`-Feld
wird ignoriert und beim nächsten Speichern entfernt; ID und Tagesmarker bleiben
erhalten. Settings → About zeigt die ID und einen Kopierknopf. Die zufällige ID
bleibt über Tage wiedererkennbar; die Datenschutztexte nennen dies ausdrücklich.

Der neue Server-Endpunkt akzeptiert genau UUID und eine nichtleere Version mit
höchstens 32 Zeichen. Er vergibt den UTC-Tag selbst. Die Tabelle hat genau drei
Spalten und den Primärschlüssel `(install_id, day)`. Doppelmeldungen verändern
die erste Meldung des Tages nicht. Ausgeschlossene UUIDs werden bestätigt, ohne
gespeichert zu werden. Das einfache In-Memory-Limit verwendet UUIDs, keine IPs.
Die Bereinigung läuft über einen Hintergrundjob im API-Lebenszyklus: einmal
täglich sowie beim Start nach einer Pause werden Einträge älter als 90 Tage
gelöscht. Die Prüfung auf einen neuen UTC-Tag erfolgt stündlich.

Die private Statistik zählt eindeutige IDs für heute, sieben und dreißig UTC-
Kalendertage einschließlich heute. Die Versionsaufteilung ordnet jede aktive
ID einmal ihrer zuletzt gemeldeten Version zu. GET /v1/usage/stats benötigt
X-EDFrame-Admin-Token, wird konstantzeitlich verglichen und liefert ohne bzw.
bei falschem Token 401. Kein CORS, keine IDs in der Antwort, kein Eintrag in
/v1/status; Antworten sind nicht cachebar. Eine leere Versionsverteilung ist
ein leeres Objekt. Die IDs sind eine Näherung für Installationen: kopierte oder
gelöschte Config-Dateien beeinflussen die Zuordnung.

Geänderte bzw. neue Dateien dieser Aufgabe:

- `ed_companion/integrations/usage_ping.py`: ID, Abschaltbedingungen, Tageslimit und Request.
- `ed_companion/phase14/controller_usage.py`: Hintergrundjobs,
  ID-Anzeige und Kopieren.
- `ed_companion/phase14/controller.py`: Initialisierung und Timer-Abschaltung.
- `Main.qml`: Erklärung in Connections, About-Zugang und ID mit Kopierknopf.
- `qml/components/OnboardingWizard.qml`: Erklärung der automatischen Zählung.
- `ed_data/i18n/{en,de,es,fr}.json`: vier neue Keys und aktualisierter Hilfstext.
- `.gitignore`: Installations-Config vom Einchecken ausgeschlossen.
- `server/catalog_service/edframe_catalog/usage.py`: Validierung, SQL, Ausschlüsse
  und Aufbewahrungsjob.
- `server/catalog_service/edframe_catalog/api.py`: neue Routen und Lebenszyklus.
- `server/catalog_service/edframe_catalog/schema.sql`: additive Tabelle und Index.
- `server/catalog_service/compose.yaml`: Admin-Token und Ausschlüsse nur an API.
- `README.md`, `server/catalog_service/README.md`: Datenschutz und Betreiberinfos.
- `tests/test_usage_ping.py`, `tests/test_usage_qml.py`,
  `server/catalog_service/tests/test_usage.py`: neue Tests.
- `tests/test_onboarding.py`: Erklärung vorhanden, ehemaliger Schalter entfernt;
  andere Einstellungen bleiben beim Überspringen erhalten.
- Website: `C:/Users/Gerri/Documents/Codex/2026-10-09/ed-frame-fortsetzung-1-5-43/github-page/index.html`:
  sichtbare FAQ und passende FAQ-Strukturdaten; ausschließlich lokal geändert.

Prüfungen:

- Nach der Schalterentfernung erneut alle 127 App-/UI-/Übersetzungs-/Speicher-/
  Release-Contract-Tests bestanden (65,3 Sekunden). Auch ein früheres lokales
  `enabled: false` blockiert die automatische Zählung nicht mehr.
- Bei der vorherigen Umsetzung alle 221 Servertests bestanden; der Servercode
  blieb bei dieser Schalterentfernung unverändert. Die ASGI-Contracts durchlaufen echte
  FastAPI-Validierung und Antworten; INSERT/SELECT/DELETE sowie die neue
  Tabellen-Eindeutigkeit wurden in einer isolierten SQLite-Datenbank ausgeführt.
- Die Windows-Sandbox kann asyncio-TCP-Socketpairs nicht verwenden. Für die
  bestehenden in-process-ASGI-Regressions wurde deshalb lediglich Thread- und
  Timeout-Dispatch synchron adaptiert; unerwartetes suspendierendes I/O scheitert.
  Der reproduzierbare lokale Runner liegt unter `outputs/run_usage_server_tests.py`.
- Bei der vorherigen Umsetzung zwei vollständige Offline-App-Smokes bestanden,
  je 33 Prüfpunkte, mit beiden
  Seitenlader-Varianten und ohne QML-Laufzeitfehler.
- Onboarding weiterhin über alle neun Seiten, sechs Themes, vier Sprachen und
  100/115/150 Prozent Skalierung geprüft.
- YAML geprüft: Token und Ausschlüsse gehen nur an API, nicht an Collector.
- FAQ-Strukturdaten und sichtbarer Text stimmen überein; alle vier Sprachen haben
  die neuen UI-Keys. `git diff --check` ohne Fehler.
- Caddyfile und Dockerfile unverändert; keine Logging-, FORWARDED_ALLOW_IPS-,
  --forwarded-allow-ips- oder --proxy-headers-Änderungen.

Für deinen manuellen Test die lokale Quell-App starten und die Erklärtexte in
Connections und im Onboarding prüfen. Unter Settings → About die ID kopieren
und nach Neustart vergleichen. Ein Development-Build sendet dabei absichtlich
keine Pings. Die laufende veröffentlichte App wurde nicht ersetzt.

Vor einer späteren Aktivierung bleibt ein echter isolierter PostgreSQL-Test der
Migration und Endpunkte sinnvoll: Hier standen weder PostgreSQL noch Docker
lokal zur Verfügung. Das laufende Datenbankschema wurde nicht verändert. Für
den späteren Betrieb sind die additive Migration und ein privater
EDFRAME_ADMIN_TOKEN nötig; der alte verifizierte Schema-Fingerprint darf für
dieses geänderte Schema nicht wiederverwendet werden. EDFRAME_USAGE_EXCLUDED_IDS
vor der ersten Sammlung konfigurieren, wenn eigene Testinstallationen nicht
mitzählen sollen. Die Website-FAQ ist noch nicht veröffentlicht.

Keine produktiven Profile oder Serverdienste geändert. Kein Commit, Push,
Tag, Release, Workflow oder Deploy. Die vorherigen lokalen Optimierungen sind
erhalten; die hier beschriebenen Serveränderungen wurden darauf ergänzt.
