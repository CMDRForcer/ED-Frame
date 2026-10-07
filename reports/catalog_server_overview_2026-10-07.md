# Serverübersicht und nächste Datenanbindungen

## Umsetzung

Settings → Connections → ED-Frame Catalog Server zeigt sechs responsive Kennzahlenkarten:
Systeme/Stationen, Warenmärkte, Mining-Nachweise, Modulangebote, Schiffswerften,
State Finds/HGE. Größen sind erklärt: Warenzeilen sind keine Stationen;
Verfügbarkeit ist kein Preisnachweis; BGS ist keine bestätigte aktive HGE.

Zusätzlich: Marktzeilen aktualisiert innerhalb 1 h/24 h, EDDN-Eingang/Nutzungsanteil/
Fehler der letzten 24 h, erfolgreiche Serverprüfung in Ortszeit. Aufklappbar:
Datenqualität und getrennte lokale Synchronisationsstände.
Fehlende Kennzahlen werden als „—“ angezeigt, nicht als erfundene Null.
Datenschutz-, Uploadstatus- und Aktivitätszeilen sind auf 12 px vergrößert;
Aktivitätszeilen umbrechen statt rechts abgeschnitten zu werden.
Keine zusätzlichen Requests, keine Veränderung der Freigaben, Caches oder Persistenz.
Deutsch ergänzt; neue spanische/französische Texte verwenden vorerst Englisch.

Betroffen: Main.qml, qml/components/CatalogServerOverview.qml,
controller_navigation.py (Statusmetadaten), vier Übersetzungskataloge,
tests/test_edframe_catalog_status.py.

## Größte Hebel – Einschätzung anhand des Codes

1. **Regionale HGE-/State-Finds-Abfragen.**
   Der lokale Merge behält höchstens 10.000 Beobachtungszeilen
   (state_find_catalog.py: merge_edframe_state_find_page; controller_navigation.py:
   HGE_OBSERVATION_LIMIT). Das ist nicht die Anzahl verschiedener Systeme.
   Globale Synchronisation kann räumlich wichtige Daten verdrängen.
   Abfrage nach Position/Radius und gesuchtem Material plus regionaler Cache-
   Priorisierung ist der größte nächste Hebel. BGS-Kandidaten und echte
   Signalmeldungen müssen weiterhin getrennt bleiben.

2. **Stationsdienste in NAV/Operations.**
   Der Server besitzt Pad, Anflugdistanz, Dienste und Stationsmetadaten.
   /v1/stations/search filtert derzeit System, Dienst und Pad, aber nicht
   Koordinaten/Radius; sortiert nach Beobachtungszeit. Ein regionaler Endpunkt
   und ein gemeinsamer Dienste-Finder würden diese Daten praktisch nutzbar machen.
   Material-Trader/Techbroker erst vollständig ersetzen, wenn deren Untertypen
   verlässlich vorliegen: trader_search.py benötigt manufactured/raw/encoded
   beziehungsweise Guardian/Human. Generischer Dienst allein reicht nicht.

3. **Mehrere Module an einer Station finden.**
   Shipyard/Outfitting ruft bereits fetch_edframe_station_offers auf.
   Ausbau statt neue Grundanbindung: gemeinsame Angebotsabdeckung für eine
   Einkaufsliste, getrennte Preisnachweise, passende Slots, lokale Freischaltungen/
   Permits, Pad und Anflugdistanz. Keine Änderung der Material-Allokation nötig.

4. **Mining: Nachweise verdichten statt nur Katalogzahlen vergrößern.**
   Märkte, Ringe, Powerplay und Community-Erträge sind bereits angebunden.
   Wenige gemessene Orte können keine galaxisweite High-Yield-Gewissheit liefern.
   Gezielt weitere Messungen sammeln, Quellen/Alter je Ergebnis erklären und
   regionale Vollständigkeit prüfen. Große Ringzahl ersetzt keinen Ertragsnachweis.

Reihenfolgeempfehlung: 1 → 2 → 3; 4 laufend verbessern.
Dies sind Vorschläge, noch keine Umsetzung zusätzlicher Anbindungen.

## Prüfung und Grenzen

- 885 App-Regressionstests grün, einschließlich echter Main.qml-Smoke-Tests.
- 11 Serverstatus-Vertragstests nach Erweiterung grün.
- Komponente unter Qt/PySide6 offscreen bei 1280 und 650 px gerendert;
  aufgeklappter Detailbereich ebenfalls geprüft, Exit-Code 0.
- Vorschaubilder verwenden ausdrücklich Beispieldaten, keine aktuelle Live-Messung.
- Keine neue Prüfung/Änderung auf dem Produktionsserver in diesem UI-Arbeitsschritt.
- Kein Commit, Push oder Release vorgenommen. App-Neustart lädt die Änderungen.
