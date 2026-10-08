# MiningFinder: wiederholte regionale Abfragen reduziert

8. Oktober 2026. Punkt 2 des aktuellen Fahrplans nach dem QML-Slot-Fix:
bereits geladene, ausreichend aktuelle Regionaldaten wiederverwenden.

## Änderung

- Vollständig durchlaufene Ring-Abfragen werden höchstens **300 Sekunden**,
  Powerplay-Abfragen höchstens **60 Sekunden** wiederverwendet. Das Fenster
  beginnt vor dem ersten Abruf, nicht nach dem Download. Lesen verlängert es nicht.
- Abfragebindung an Server, Koordinaten, Radius und bei Ringen die Ware;
  zusätzlich separate Cache-Instanzen je Profil, Profilgeneration und Datenpfad.
  Marktfilter ändern die unabhängige regionale Ring-/Powerplay-Abdeckung nicht.
- Fehler, Teilantworten, fehlende Paginierungsnachweise, bekannte widersprüchliche
  Snapshots und abgebrochene Anfragen erzeugen keinen wiederverwendbaren Eintrag.
  Fehlende Optimierung führt immer zum bisherigen vollständigen Abruf zurück.
- Marktanbieter werden bei jeder Suche weiterhin abgefragt. Gezielte
  Routenprüfungen einschließlich Powerplay-Batches bleiben unverändert aktiv.
- Originale Beobachtungszeiten bleiben erhalten. Powerplay-Reuse endet zusätzlich
  vor Ablauf der bestehenden 24-Stunden-Frischegrenze; auch Uhrzeitsprünge werden
  geprüft. Ein Cachetreffer ist keine neue Serversichtung oder Bestätigung.
- Explizites „Refresh current system“ verwirft die regionale Wiederverwendung
  für die nächste Suche. Reset, Profilwechsel und Ein-/Ausschalten des Servers
  ersetzen den Cache ebenfalls. Verzögerte Arbeiter behalten nur ihre alte Instanz.
- Maximal vier Einträge, insgesamt höchstens **8 MiB komprimierte Nutzlast**,
  64 MiB expandiert und 50.000 Zeilen je Eintrag. JSON-Verarbeitung in Blöcken
  zu 128 Zeilen statt eines großen, GIL-blockierenden Gesamtdokuments.
  Verarbeitung erfolgt auf Netzwerk-Arbeitern; keine neue Cachedatei.
- Status meldet „recent region reused“, nicht „snapshot unchanged“ ohne neuen
  Servernachweis. Bestehende versionierte Snapshot-Revalidierung bleibt erhalten.

## Messung am öffentlichen Server

`python -B tools/benchmark_mining_region_reuse.py --radius 50`

Shanteneri, Platinum, 50 LY, Large Pad, Marktalter 1 h. Rein öffentliche GETs,
keine App-Initialisierung, Uploads, Nutzerdateien oder Serveränderungen.
Unmittelbare Folgesuche im gleichen Prozess, kein Disk-Snapshot.

| Finaler Lauf | Erster Abruf | Folgesuche |
| --- | ---: | ---: |
| Gesamte Datenabrufphase | 7,555 s | 0,712 s |
| HTTP-Abfragen | 5 | 2 |
| Ring-Abruf | 7,554 s | 0,003 s |
| Powerplay-Abruf | 0,581 s | 0,005 s |
| Markt-Abruf | 0,837 s | 0,711 s |

269 Ringe und 787 Powerplay-Zeilen vor/nach Wiederverwendung vollständig identisch,
einschließlich Beobachtungszeiten und verschachtelter Daten. 71 Marktzeilen wurden
jeweils neu abgefragt. Zwei Cacheeinträge mit zusammen 54.521 Byte Nutzlast.
Domänen laufen parallel; ihre Zeiten dürfen nicht addiert werden.

Ein vorheriger Lauf vor der blockweisen Serialisierung zeigte 11,239 → 0,815 s,
269 identische Ringe und 790 identische Powerplay-Zeilen. Unterschiedliche
öffentliche Bestände und Serverlast zwischen Läufen sind erwartbar; diese
Einzelmessungen sind keine feste Geschwindigkeitsgarantie.

Die 87 → 2 Abfragen des Regressionstests sind **simulierte** 26 Ringseiten,
59 Powerplay-Seiten und zwei Marktabfragen bei realer Client-Paginierung.
Sie sind kein erneuter Live-250-LY- oder 100-Routen-Gesamtapp-Benchmark.

## Grenzen und Nachteile

Neue Ringdaten können innerhalb des fünfminütigen Fensters, neue Powerplay-
Meldungen innerhalb einer Minute noch nicht im regionalen Bestand erscheinen.
Gezielte Prüfungen bleiben unabhängig; manuelles Refresh umgeht die Wiederverwendung.
Das ist begrenzte Abrufwiederverwendung, keine revisionsbestätigte Live-Garantie.
Erstsuche, andere Regionen und abgelaufene/eviktierte Einträge laden weiterhin
vollständig; Cacheaufbau hat geringe zusätzliche Serialisierungskosten.

Der Abrufvergleich misst weder GUI-Latenz noch den gesamten Prozess-RAM,
Planung, Zusammenführung oder gezielte Nachprüfung. Bestehende Replan-Anlässe
und die gestufte Ergebnisanzeige sind nicht umgebaut. Punkt 3 bleibt:
100-Routen-Messung mit vollständiger Nachprüfung, RAM und Bedienbarkeit.

## Prüfungen und Auslieferung

Regressionstests decken Scope-/Serverbindung, Ablauf ohne Verlängerung,
unveränderte Zeitstempel, Mutationstrennung, Budget/Verdrängung, kleine Blöcke,
Quellfrische/Uhrzeitsprung, leere Antworten, fehlerhafte/partielle Antworten,
Abbruch, deaktivierten Server, unabhängige Wiederholung fehlgeschlagener Domänen,
Profilgeneration/Datenpfad und manuelles Refresh ab.

Abschließende Gesamtsuite: **1.146 App-Tests erfolgreich** in 117,487 Sekunden,
darunter 20 neue Cache-Regressionstests und die echten QML-Aufrufe der Nachprüfung.
`git diff --check` und die Repository-Hygieneprüfung erfolgreich.

Keine Veränderung an BGS, Ranking, Quellen-Frischegrenzen, Nutzerhistorien oder
Servercode. Keine vorhandenen Dateien gelöscht, komprimiert oder migriert.
Kein Commit, Push, Release, Serverdeploy, App-Neustart oder Herunterfahren.
