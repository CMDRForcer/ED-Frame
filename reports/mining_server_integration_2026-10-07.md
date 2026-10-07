# Mining Finder: eigene Serverdaten

## Ergebnis und Betriebsstand

Die App übernimmt Serverdaten für Ringe/Hotspots, Verkaufsmärkte, ausdrückliche
Powerplay-Fakten und gemessene Community-Erträge. Bestehende externe Quellen
bleiben Ergänzungen, da die Serverabdeckung nicht vollständig ist. Keine
Änderung an Merit-Formeln, Nachfrage-/Padfiltern, Ein-Stunden-Grenze,
Verifikationslimit von sechs Zielen oder Freigabe zum Teilen eigener Erträge.

**Server am 7. Oktober 2026 um ca. 10:23 Uhr Berlin deployed.** Die neue
Powerplay-Sammlung und ihr Endpunkt sind aktiv und liefern HTTP 200.
Die lokalen Änderungen sind weiterhin nicht committed oder gepusht.
Bei Serverausfall behält die App Journal-/EDDN-/EDSM-Daten.
Kein Anspruch, den gesamten Mining-Bedarf bereits ausschließlich aus dem
Server abzudecken.

## Änderungen

| Bereich | Änderung | Dateien/Funktionen |
| --- | --- | --- |
| Ringe/Hotspots | Abfrage im Suchradius statt nur im aktuellen System, maximal 200 Ergebnisse. Alte physische Ringdatensätze bleiben abrufbar; die bestehende Freshness-Prüfung nutzt weiter den Beobachtungszeitpunkt. Spansh ergänzt unvollständige oder veraltete aktuelle Systemdaten. | `mining_finder.fetch_edframe_mining_candidates`, `controller_navigation._start_mining_market_refresh`, `refreshMiningFinder` |
| Verkauf | Bereits bekannte Koordinaten wiederverwenden und exakte Stunden-Altersgrenze an den Server schicken statt Aufrundung auf ganze Tage. Externe Marktindizes ergänzen weiter die begrenzte zentrale Auswahl. | `mining_market._fetch_edframe_catalog_markets`, `fetch_market_imports` |
| Powerplay | EDDN-Journal-Fakten anonym projizieren und neuesten Snapshot je System speichern. Ältere Meldungen überschreiben keine neueren. Regionale API mit 24-h-Abfragefenster und maximal 200 Systemen. Presence ist niemals automatisch Control. | Server: `projection.project_powerplay_snapshot`, `database.upsert_powerplay_snapshot`, `collector`, `schema.sql`, `api.search_mining_powerplay`; Client: `mining_powerplay.fetch_edframe_powerplay` |
| Merit | Beim Zusammenführen mehrerer Kontrollbeobachtungen gewinnt der neuere Zeitstempel unabhängig von Listenreihenfolge. Regeln zur Eignung unverändert. | `mining_planner._powerplay_index` |
| High Yield | Überlappende Community-Snapshots nicht addieren; aktuelle Snapshot-Messwerte nutzen. Community-/Local-Herkunft auch pro Commodity erhalten und ehrlich beschriften. Kein gemessener Ertrag ohne Messwerte. | `mining_finder.merge_mining_candidates`, `mining_planner._secondary_resources`, `plan_mining_routes` |
| Diagnose/Fehlertoleranz | Ring- und Powerplay-Ergebnisse unabhängig vom Erfolg der Markt-Abfrage übernehmen, aber niemals nach Profilwechsel. Begrenzte Auswahl und nicht erreichbare Serverbereiche im Status nennen. | `controller_navigation._finish_mining_market_sync`, bestehender Beobachtungs-Batch |

Die zusätzlichen Abfragen laufen im vorhandenen Netzwerk-Worker. Es werden
keine Netzwerkanfragen im QML-/UI-Thread ausgeführt. Die bestehenden
Persistenzverfahren, INARA-/EDDN-Versandqueues und HGE-Regeln wurden nicht
umgebaut. Neue Daten nutzen den bestehenden Beobachtungs-Batch; ihre Übernahme
kann daher bis zum nächsten Batch erfolgen, nicht zwingend sofort mit dem
Marktergebnis.

## Echte Serverprüfung am 7. Oktober 2026

Nur lesende Prüfung der öffentlichen API, kein Zugriff auf private Commander-
oder Produktions-DB-Daten:

- Cubeo-Koordinaten aus eigenem Server: `[128.28125, -155.625, 84.21875]`.
- Platinum, 100 LY: **16 Ringe**, unter dem 200er-Limit; keine Ertragsmessungen
  in dieser Stichprobe.
- Platinum-Märkte, 100 LY, Alter maximal 1 h: **22 Angebote**.
- Beispiel: HIP 3254 / The Knight's Watch, MarketID `4226259971`,
  `sellPrice=300702`, `demand=8898`, Beobachtung `2026-10-07T08:06:21Z`.
- Beispiel: Osane / Bell Vision, `sellPrice=240778`, `demand=602`. Dieser Wert
  wird korrekt importiert, aber bei einem Nachfrage-Minimum von 5000 weiter
  ausgeschlossen. Import ist keine Eignungsbestätigung.
- Vor Deployment: `/v1/mining/powerplay` HTTP 404. Nach Deployment: **HTTP 200**.
  Die neue Tabelle enthielt bei der ersten Nachkontrolle bereits zehn echte
  Systeme. Eine spätere App-Client-Stichprobe um FAUST 3725 empfing fünf Fakten,
  davon drei mit ausdrücklich gemeldetem Controller. Beispiel: Orishis,
  Edmund Mahon, Beobachtung `2026-10-07T08:27:48Z`.

Der Status-Snapshot von 08:02 UTC meldete insgesamt 508.349 Mining-Sites,
3.597 Sites mit Hotspots (0,7 %) und 51 geteilte Ertragsproben an zwei Sites.
Die 4.328.539 Marktzeilen betreffen **alle Commodities**, nicht nur Mining.
Das sind Bestandszahlen, keine Garantie einer vollständigen oder frischen
Mining-Abdeckung. Eine weltweite High-Yield-Rangliste aus tatsächlichen
Messungen ist damit noch nicht belastbar.

## Verifikation

- App-Regressionssuite: **885 Tests grün** im Gesamtlauf nach Deployment und
  ergänzter HGE-Quellenanzeige (zuvor 883 für die Mining-Änderungen).
- Mining-Verträge/Regressionen nach letzten Funktionsänderungen: 166 Tests grün.
- Zusätzlicher Vertrag für unabhängige Übernahme bei Marktfehler und Verwerfen
  nach Profilwechsel: grün; insgesamt acht neue Integrationsverträge.
- Server-Verträge: 50 Tests grün, inklusive fünf neuer Powerplay-Verträge.
- Server-SQL/API zusätzlich über Mock-Verbindungen geprüft. Der neue
  Powerplay-Pfad ist inzwischen auch live belegt: Collector → PostgreSQL →
  öffentliche API → App-Parser. Kein gespielter Merit-Verkauf und keine neue
  Prospector-Probe.
- Separater QML-Smoke-Test der echten App: **PASS**, `mining-finder: PASS`,
  **Exit-Code 0**. QML-Ladetests sind zusätzlich Teil der Gesamtsuite;
  Live-Stichprobe und automatische Tests ersetzen keinen manuellen Ingame-Test.

## Deployment und nächste Prüfung

Deployment nach ausdrücklicher Freigabe erfolgt. Vorher verifizierter
PostgreSQL-Dump (205 MB), Quellcode-Sicherung und Rückfall-Tags der alten Images
unter `/opt/edframe-deploy-backups/mining-20261007`. Nur API und Collector neu
gebaut und gestartet; DB und Caddy blieben in Betrieb, keine Volumes entfernt.
API und DB anschließend healthy, Collector verbunden, `/healthz` HTTP 200.
`ensure_schema()` hat die Snapshot-Tabelle idempotent angelegt; der Collector
sammelt künftig eintreffende EDDN-Kontrollmeldungen. Historische Fakten werden nicht
erfunden oder automatisch rückwirkend aus EDSM-Präsenz abgeleitet. Anschließend
mit wachsendem Bestand Abdeckung und tatsächliche Ingame-Merit-Routen prüfen.
