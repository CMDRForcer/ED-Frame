# MiningFinder: Powerplay-Abgleich und Nachladen

Stand: 8. Oktober 2026. Bestehende Performance-Änderungen im Arbeitsverzeichnis
bleiben erhalten. Keine Benutzerprofile, Journale oder historischen Dateien
wurden geändert, bereinigt oder migriert. BGS-Prognosen bleiben unverändert.

## Funde und Fixes

- Die regionale Powerplay-Abfrage las nur die ersten 200 zuletzt beobachteten
  Systeme. API und Client unterstützen jetzt eine Fortsetzung über `nextCursor`.
  Wiederholte Cursor, ältere Server und fehlgeschlagene Fortsetzungen bleiben
  ausdrücklich als unvollständig gekennzeichnet; nutzbare Fakten gehen nicht verloren.
- Die Routenprüfung begann bereits während des regionalen Abrufs. Sie wartet
  jetzt auf dessen Abschluss, den zugehörigen Ring-Merge und die Routenberechnung.
  Suchwechsel werden auch unmittelbar vor dem verzögerten Prüfaufruf kontrolliert.
- Powerplay wurde über Ringabfragen vermeintlich nachgeprüft. Fehlende Fakten
  werden nun separat für Bergbau- UND Verkaufssysteme gesammelt, dedupliziert
  und über einen indexgestützten System-Batch abgefragt. Alle bis zu 100
  angezeigten Routen werden berücksichtigt, nicht nur die ersten 30.
- Frische explizite Fakten verhindern erneute Abfragen. Leere Antworten und
  Fehler bekommen kurze Wiederholsperren, aber keine bestätigte Merit-Eignung.
  Andere Suchziele lösen keine zusätzliche Powerplay-Nachprüfung aus.
- Suchantworten veröffentlichen Powerplay-Fakten vor den Marktbenachrichtigungen,
  ohne den 30-Sekunden-Relay-Batch abzuwarten. Das gilt auch bei einem unabhängigen
  Marktfehler. Große Ring-Merges bleiben auf dem bestehenden Hintergrund-Worker.
- Neue Powerplay-Fakten können nicht mehr von älteren Ring-/Marktmetadaten
  überschrieben werden. Explizite neuere Unoccupied-Fakten löschen alte
  Controller-Behauptungen; reine EDSM-Präsenz wird weiterhin nicht als Kontrolle gewertet.
- Die Erklärung bewahrt den tatsächlichen fehlenden Nachweis, etwa den Zustand
  des Verkaufssystems, statt pauschal dem Bergbausystem die Datenlücke zuzuschreiben.
- Die Live-Prüfung lieferte mehr als 20.000 Powerplay-Fakten. Das bisherige lokale
  Merge-Limit hätte die vollständig abgefragte Region anschließend erneut gekürzt.
  Region, Einzelprüfung und Relay verwenden nun denselben verlustfreien Merge:
  je System/Power bleibt der neueste Fakt erhalten, ohne eine wachsende Liste
  wiederholter Meldungen. Unveränderte Relay-Fakten lösen ebenfalls keinen Save/Replan aus.

## Kompatibilität und Betriebsstand

Ältere Server werden erkannt. Für fehlende bekannte Orte verwendet die App
übergangsweise kleine Powerplay-Radiusabfragen, keine erneuten Ring-Downloads.
Das benötigte API-Update wurde nach ausdrücklicher Nutzerfreigabe am
8. Oktober 2026 gegen 06:08 UTC auf `135.125.200.69` deployt. Nur die Funktion
`search_mining_powerplay` wurde ersetzt; ein AST-Abgleich bestätigt, dass
der übrige API-Quellcode unverändert blieb. Das neue Image basiert auf dem
zuvor laufenden API-Image. Nur der API-Container wurde neu gestartet;
Datenbank, Collector und Caddy behielten ihre Container-IDs. Keine Datenbankmigration.

Rückfallkopie: `/opt/edframe-deploy-backups/powerplay-20261008-01/`.
Vorheriges Image: `edframe-catalog-api:before-powerplay-20261008-01`.
API-Healthcheck und öffentliche Statusabfrage: HTTP 200.

Noch kein Commit, Push oder App-Release in diesem Durchgang. Die App-Fixes
liegen im Quellcode; eine bereits installierte ältere EXE enthält sie noch nicht.

## Live-Prüfung

- App-Client, 500 LY um die für Shanteneri verwendeten Koordinaten:
  **13.163 Systeme / 35.172 Fakten**, 66 Seiten, `bounded=false`.
  Rund **4,55 Sekunden** und 12,68 MB Antwortdaten auf diesem Rechner.
  Dies ist die aktuelle regionale Abdeckung, keine Garantie für jedes System der Galaxis.
- Exakter Batch mit 200 Namen: **eine HTTP-Anfrage, rund 64 ms**.
  199 vorhandene Systeme geliefert; ein absichtlich unbekannter Testname blieb
  ohne Fakten. Leere Daten werden nicht zu bestätigter Merit-Eignung.
- Zwei Cursor-Seiten lieferten unterschiedliche Systeme. Ungültiger Cursor:
  HTTP 400. Regionale Aufrufe ohne neue Parameter bleiben kompatibel.
- Echte fehlende oder zu alte EDDN-Beobachtungen bleiben `POWERPLAY_DATA_MISSING`.
  Aus bloßer Power-Präsenz wird weiterhin keine Kontrolle abgeleitet.

## Prüfung

- 261 relevante App-/Mining-/Responsiveness-Tests: grün.
- 100 Katalogserver-Tests: grün.
- Echter MiningFinder-QML-Test: Ergebnisse, Auswahl und Scrollanker bleiben
  erhalten; die Nachprüfung startet erst nach dem regionalen Abruf.
- Synthetischer Abgleich von 20.000 gespeicherten Fakten mit 2.000 Wiederholungen:
  ca. 11 ms auf diesem Rechner; unveränderte Fakten erzeugen keinen neuen Save/Replan.
- Zusätzlicher synthetischer Controller-Abgleich in Größe der Live-Antwort:
  35.172 Fakten vollständig erhalten, erstmalige Veröffentlichung ca. 33,3 ms,
  unveränderte Wiederholung ca. 34,4 ms. Genau ein gemockter Save; keine Profildatei
  wurde für die Messung geschrieben. Dies misst den Merge, nicht die gesamte Suchdauer.
- Gesamtlauf vor den letzten Zusatztests: 1.109 Tests, davon ein fehlgeschlagener
  Main.qml-Ladetest. Separat reproduziert: Loader des Engineers-Tabs meldet
  `Cannot create delegate`, obwohl die einzelnen Seitenprüfungen einschließlich
  MiningFinder erfolgreich waren. Kein Fehler wird ausgeblendet oder als grün verbucht.
- Abschließender Gesamtlauf mit produktionsnahen asynchronen Seiten-Loadern:
  **1.115 Tests grün** in 105,7 Sekunden (`PHASE14_SMOKE_ASYNC_PAGES=1`).
- Die beiden zusätzlichen Tests prüfen eine Region über 20.000 Fakten sowie
  anschließende Einzel-/Relay-Merges und unveränderte Relay-Antworten.
  Erneuter relevanter Teillauf: **64 Tests grün**.
- `git diff --check`: erfolgreich. Der separat reproduzierte synchrone
  Engineers-Loader-Smoke-Fehler ist damit nicht als behoben ausgewiesen;
  der produktionsnahe asynchrone Gesamtlauf ist davon getrennt dokumentiert.

### Nachtrag: Engineers-Diagnose geklärt

Der anschließend untersuchte Loader-Fehler war ein Fehlalarm bei einem
unmittelbar gepaarten Qt-Inkubationsabbruch während des Seitenabbaus. Die
Diagnose erkannte die neuere Loader-Vorfahren-Schreibweise nicht. Der Fix
ordnet diese Paare eng zu; alleinstehende Erzeugungsfehler bleiben Fehler.
Der neue vollständige App-Lauf besteht **1.125 Tests** ohne globalen
Async-Ausweichmodus, einschließlich synchronem Smoke-Test ohne Retry und
600 realen Engineers-Wechselaktionen in beiden Loader-Arten.
Details: [Engineers-Loader-Diagnose](engineers_loader_diagnostics_fix_2026-10-08.md).
