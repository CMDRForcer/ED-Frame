# Regionale HGE-/State-Finds-Anbindung

## Ergebnis

Die App synchronisiert State Finds jetzt im Umkreis von 250 LY um die aktuelle
Journal-Position statt über einen globalen Cursor. Der serverseitige API-Teil
ist produktiv bereitgestellt; die lokale App benötigt einen Neustart.

- Initialer Abruf und Delta-Cursor sind an exakte Position und Radius gebunden.
- Bei Ortswechsel wird ein neuer Erstabruf begonnen, auch wenn der globale
  alte Cursor bereits weiter fortgeschritten war.
- Automatische Standortwechsel-Abrufe sind auf höchstens einen neuen Lauf pro
  Minute gebündelt; Folgeseiten verwenden weiterhin das bestehende 500er-Limit.
- Fehlende/ungültige Position: kein globaler Ersatzabruf, lokale Daten bleiben.
- Ergebnisse eines alten Standorts oder Profils werden verworfen.
- Server bestätigt die Region ausdrücklich; ein alter Server, der Parameter
  ignoriert, wird nicht als erfolgreiche regionale Versorgung akzeptiert.
- Bei Überlauf des unverändert 10.000 Zeilen großen Caches: lokale Journal-/
  manuelle Nachweise zuerst, dann die nächsten Serverdaten. Verdrängte aktive
  Zeilen und abgelaufene Zeilen gehen über den bestehenden History-Archivierer.
- Die vorhandene Persistenzreihenfolge bleibt erhalten: Archiv, Fakten, Cursor.
  Schreibfehler lassen den Cursor unverändert, damit die Seite erneut gelesen wird.
- BGS bleibt BGS_PREDICTION/POSSIBLE; keine Hochstufung zu bestätigter HGE und
  keine künstliche Verlängerung der Signal-Lebensdauer.

Kein Materialfilter im Transport: Alle unterstützten State-Finds-Materialien
der Region bleiben für die vorhandenen UI-Filter verfügbar.

## Produktionsprüfung

Am 07.10.2026 um 09:08 UTC wurde mit dem echten App-Client ein vollständiger
regionaler Erstabruf um FAUST 3725 (-10.5625, 124.875, 8.71875) getestet:

| Messung | Ergebnis |
|---|---:|
| Radius | 250 LY |
| Seiten | 22 |
| BGS-Snapshots | 10.773 |
| Aktive Signalmeldungen | 0 |
| Retained Cache-Zeilen | 10.000 |
| Weitere Seiten am Ende | Nein |
| Beobachtungen außerhalb der Region | 0 |
| Größte Entfernung der behaltenen Zeilen | 157,81 LY |
| Abruf + In-Memory-Merge | 8,98 s |
| Health-Endpunkt | HTTP 200 |
| Unvollständige Koordinaten | HTTP 422 |

Das ist eine zeitabhängige Stichprobe, keine Garantie vollständiger Abdeckung.
Die 10.000 Zeilen sind Beobachtungen, nicht 10.000 verschiedene Systeme.
Der Cache bleibt bewusst begrenzt: Im dicht besiedelten Bereich können auch
innerhalb 250 LY mehr Zeilen existieren; dort erhalten nähere Daten Vorrang.
Fehlende Systemkoordinaten werden serverseitig ausgeschlossen.

Die Live-Prüfung hat weder das Spielerprofil verändert noch neue echte HGEs
beobachtet. Das App-Rendering und Schutzverhalten wurden automatisiert geprüft;
ein manueller Ingame-Ortswechsel wurde nicht durchgeführt.

## Deployment

Nur API neu gebaut/gestartet; Collector, PostgreSQL und Caddy unverändert.
Keine DB-Migration, keine Tabellen-/Datenlöschung.
Vorher gesicherte API-Quelle:
/opt/edframe-deploy-backups/state-finds-region-20261007/api-before.tar.gz
Rückfall-Image: edframe-catalog-api:before-state-finds-region-20261007.
API und DB danach healthy; Collector lief ohne Neustart weiter.

## Dateien und Tests

- server/catalog_service/edframe_catalog/api.py: optionaler regionaler SQL-Filter
  für beide Datensatzarten; globaler Vertrag für alte Clients bleibt verfügbar.
- ed_companion/navigation/state_find_catalog.py: Regionsvalidierung, Anfrage,
  Serverbestätigung und begrenzte räumliche Retention.
- ed_companion/phase14/controller_navigation.py: regionsgebundene Cursor,
  Ortswechsel-/Profilprüfung und bestehender Archiv-/Persistenzpfad.
- ed_companion/phase14/controller.py: Standortaktualisierung über stateChanged.
- server/catalog_service/README.md: API-Vertrag.
- tests/test_state_find_region.py: zwölf neue Schutz-/Vertragstests.
- server/catalog_service/tests/test_state_find_region.py: drei neue API-Verträge.

Gezielte State-Finds-Tests: 23 grün. Server-Gesamtsuite: 53 grün.
Abschließender App-Gesamtlauf: 897 grün, einschließlich der echten Main.qml-
Smoke-Tests und der zwei zusätzlichen Archiv-/Ortswechsel-Schutztests.

Kein Commit, Push oder Release in diesem Arbeitsschritt.
