# HGE / FSS: getrennte Evidenzstufen

## Umsetzung

- BGS-Kandidaten, FSS-Sichtungen ohne bekannte Laufzeit und gemeldet aktive Signale werden getrennt gezählt und beschrieben.
- Neue PostgreSQL-Tabelle `state_signal_sightings`: letzte Sichtung pro System/Typ/Fraktion/Zustand/Intensität. Keine Speicherung jeder einzelnen Scanmeldung. API/Zähler betrachten 24 Stunden; keine Löschung bestehender Katalogdaten.
- Collector -> `project_state_sightings()` -> `upsert_state_sighting_batch()` -> `/v1/sync/state-finds` (`SIGHTING`) -> `state_find_catalog.py` -> Statusübersicht.
- Unterstützt HGE, Konfliktzonen und Seeking-Meds/Foods. Carrier/Stationen/Nav-Beacons werden nicht als solche Sichtungen gezählt. Rohmeldungszahl und Sichtungszahl sind nicht gleichzusetzen.
- Positive, noch gültige Restlaufzeit bleibt Voraussetzung für aktive Signale. Untimed-Sichtungen ersetzen keine gültige timed-Beobachtung.
- Separates Opt-in, standardmäßig aus: eigene öffentliche Journal-Signale über `/v1/state-signals/observations`. Kein Commandername, Schiff, Fracht oder Journalpfad; EDDN-Sendepfad unverändert. Upload im Hintergrund, begrenzt, mit Profilwechsel-/Consent-Prüfung.
- Eine zeitlich gültige Meldung garantiert anderen Spielern nicht dieselbe USS-Instanz.

## Deployment und echte Prüfung

Freigabe des Nutzers für sechs Quelldateien, zusätzliche Tabelle und Neustart erhalten. API und Collector auf 135.125.200.69 neu gebaut und gestartet; Datenbank/Caddy nicht neu gestartet.

Backup: `/opt/edframe-deploy-backups/signals-20261007-01/`. Vorherige Images: `edframe-catalog-api:before-signals-20261007-01` und `edframe-catalog-collector:before-signals-20261007-01`.

Lesend geprüft am 2026-10-07, 11:41 UTC:

| Prüfung | Ergebnis |
| --- | --- |
| Öffentliche Health-API | HTTP 200 |
| Signal-Upload-Route mit GET (kein Upload) | HTTP 405, Route vorhanden |
| State-Finds-Sync, letzte 10 Minuten | HTTP 200, 404 BGS-Zeilen |
| Aktuelle BGS-Snapshots | 40.317 |
| FSS-Sichtungen | 0 |
| Aktive Signale | 0 |

25 Sekunden echte EDDN-Beobachtung: 20 FSS-Frames empfangen. Die vier ausgegebenen Beispiele enthalten Carrier, Stationen, NavBeacon/Installation; keine passende HGE-Sichtung darin. Das belegt Empfang, aber noch keinen positiven echten SIGHTING-Schreib-/Lesepfad. Der weiterhin leere Zähler darf nicht als erfolgreich befüllter HGE-Katalog dargestellt werden. Alte Rohmeldungen werden nicht rückwirkend importiert.

## Tests und Grenzen

- Gesamte App-Suite: 941 Tests grün.
- Server-Suite: 64 Tests grün.
- Nach letzter Zuordnung der Datenschutzhinweise: 36 Signal-/UI-Vertragstests grün.
- Erneuter isolierter QML-Smoke: 3 Tests grün, echte App ohne Runtime-Fehler mit Exit-Code 0; absichtlich injizierte Fehler werden erkannt.
- Positive Signal-/Sighting-Fälle, Privacy, TTL, Dedup, Rate-Limit und Profilwechsel mit Testfixtures geprüft.
- Kein echter Spieler-Upload ausgelöst, keine Zustimmung stellvertretend aktiviert.
- Produktions-Transaktionsschreibtest wurde von der Sicherheitsprüfung abgelehnt und NICHT ausgeführt. Datei `ops/verify-signals-transaction.py` ist dafür vorbereitet, aber ungetestet gegen Produktion.
- Noch nicht committed/gepusht. App neu starten, damit lokale Änderungen geladen werden; Opt-in in Einstellungen/Verbindungen nur bei gewünschtem Teilen aktivieren.
