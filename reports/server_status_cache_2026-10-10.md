# Zwischenspeicher für die Serverstatistik am 10.10.2026

Der öffentliche Statistikendpunkt `/v1/status` verwendet jetzt einen gemeinsam
genutzten PostgreSQL-Zwischenspeicher. Serverversion 0.9.4 ist produktiv aktiv.
Der zuvor einzeln gemessene Abruf von 41,93 Sekunden dauerte nach der Umstellung
in 30 Kontrollabrufen zwischen 0,059 und 0,178 Sekunden. Die bestehende App 1.0.8
verwendet dieselbe Schnittstelle und profitiert beim nächsten Statistikabruf;
eine neue App-Version ist dafür nicht erforderlich.

## Verhalten

- Ein Hintergrundthread prüft alle 30 Sekunden, ob der Datenstand mindestens
  fünf Minuten alt ist. Nur ein API-Worker berechnet den neuen Stand; eine
  PostgreSQL-Advisory-Sperre verhindert doppelte Arbeit zwischen Prozessen.
- Während der Berechnung erhalten Abrufe weiterhin den letzten vollständigen
  Datenstand. Das Ergebnis wird anschließend atomar ersetzt und bleibt über
  API-Neustarts erhalten. Ein HTTP-Abruf führt keine Katalog-Gesamtscans aus.
- Bestandszahlen, Vollständigkeit und 24-Stunden-Auswertungen stammen aus
  derselben schreibgeschützten Repeatable-Read-Transaktion. `generatedAt`
  bezeichnet deren tatsächlichen Datenstand und wird beim Abruf nicht erneuert.
- Der aktuelle Collector-Zustand wird bei jedem Abruf separat mitgelesen.
  Die zusätzlichen Felder `cache.ageSeconds`, `cache.refreshSeconds` und
  `cache.stale` beschreiben das Alter des Statistikstands.
- Fehler bei der Aktualisierung erhalten den letzten guten Stand. Er darf
  höchstens 30 Minuten alt sein; danach oder bei einem noch ungefüllten Cache
  antwortet der Endpunkt mit HTTP 503 und `Retry-After: 5`.
- Die Berechnung verwendet keine parallelen SQL-Worker. Abfragen sind auf
  60 Sekunden und die gesamte Transaktion auf 120 Sekunden begrenzt. Die
  Cache-Leseabfrage hat ein Statement-Limit von zwei Sekunden.

## Messungen und Prüfung

| Prüfung | Ergebnis |
|---|---|
| Zehn einzelne HTTPS-Abrufe | 0,059–0,075 s |
| Zwanzig HTTPS-Abrufe mit acht parallelen Clients | 0,085–0,178 s |
| Median aller 30 Abrufe | 0,104 s |
| Erste vollständige Hintergrundberechnung beim Rollout | 25,892 s |
| Server-Unit-Tests mit geänderten Quellen | 172 bestanden |
| Isolierter Test mit echtem PostgreSQL | Bestanden; eigenes Schema anschließend entfernt |

Alle 30 Abrufe lieferten HTTP 200 und dieselben Statistikfelder und Zähler
für ihren gemeinsamen Datenstand. Der PostgreSQL-Test prüfte die gegenseitige
Sperre, schnelles Lesen während einer laufenden Aktualisierung, Erhalt des
vorherigen Stands bei Fehlern und Ablehnung eines abgelaufenen Stands.

Auch die echte automatische Aktualisierung wurde ohne manuellen Eingriff
beobachtet: `generatedAt` wechselte von `2026-10-10T14:14:29.038550Z` auf
`2026-10-10T14:19:42.703891Z`. Die Zahl der Marktzeilen stieg dabei von 6.496.573
auf 6.499.291. Während der Berechnung antwortete der bisherige Stand in
0,077–0,101 Sekunden; der erste beobachtete neue Stand in 0,078 Sekunden.
Der live mitgelesene Collector meldete weiterhin null Fehler.

Die Laufzeiten sind Kontrollmessungen von diesem Windows-Client zu diesem
VPS. Die frühere Laufzeit ist eine einzelne Ausgangsmessung. Daraus wird
keine allgemeine Beschleunigung der Mining-Suche oder der gesamten UI abgeleitet.

## Rollout und Projektstand

Vor dem Wechsel wurde ein vollständiger Datenbank-Dump mit 376.980.384 Byte
erstellt und vollständig mit `pg_restore --file=/dev/null` gelesen. SHA-256:
`68e8cd8d2458a162fa8208d701d4d56c75271790e96965eaacbf403eac56bf69`.
Backup, vorige Quellen und Rollback-Konfiguration liegen unter
`/opt/edframe-deploy-backups/status-cache-0.9.4-20261010`.

Der neue Cache wurde vor dem API-Wechsel gefüllt. Aktiv ist das Image
`edframe-catalog-api:0.9.4-status-cache-20261010`. Nur der API-Container wurde
ersetzt; Container-IDs und Startzeiten von PostgreSQL, Collector und Caddy
blieben gleich. Der öffentliche Health-Endpunkt bestätigt Version 0.9.4.

Die lokalen Änderungen umfassen `status_cache.py`, die API-Einbindung, die
Singleton-Cachetabelle, die Serverversion, acht neue Tests und die README.
Die Änderungen der vorherigen Speicherbereinigung bleiben erhalten und werden
gemeinsam mit dem Statistikcache auf `main` veröffentlicht. Für diese
Serverumstellung ist kein neuer App-Release erforderlich; App 1.0.8 bleibt
unverändert.

Rohmessungen und Rollout-Helfer liegen im Chat-Arbeitsordner unter
`outputs/server-status-cache-20261010`.
Insbesondere enthalten `live-verification.json`,
`automatic-refresh-verification.json` und `rollout.txt` die Messungen und
Rollout-Ergebnisse.
