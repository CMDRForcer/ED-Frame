# Marktsynchronisierung optimiert – 12.10.2026

Die optimierte Marktsynchronisierung ist auf dem Server aktiv. Die bestehende
App 1.0.9 verwendet sie über denselben Endpunkt; ein App-Update ist nicht nötig.
Quellcode und Tests bleiben lokal uncommittet und ungepusht.

## Änderung

Die vorherige Abfrage verknüpfte Markt-, Stations- und Systemdaten für den
gesamten passenden Bestand, bevor sie die nächste Seite auswählte. Der
zusammengesetzte Zeitpunkt GREATEST(Markt-Eingang, Stations-Eingang) erschwerte
die Nutzung der vorhandenen Empfangsindizes und verursachte große temporäre
Schreibmengen.

Die neue Abfrage zerlegt die Änderungsschlüssel in zwei disjunkte, geordnete
Ströme: Markt-Eingänge, die mindestens so neu wie die Station sind, und
neuere Stations-Eingänge mit älteren Marktzeilen. Aus beiden werden höchstens
die für eine Seite benötigten Schlüssel kombiniert. Erst diese kleine Auswahl
wird mit vollständigen Stations- und Systemdaten angereichert. Vorhandene
Indizes genügen; es gab keine Schemaänderung, neuen Indizes oder global erhöhte
Speichereinstellungen.

Zeitstempel, Warenfilter, Felder, Cursorformat und Sortierung bleiben erhalten.
Eine reine Stationsänderung überträgt weiterhin die vorhandenen Waren mit
aktualisierten Stationsdaten und ursprünglichen Preis-Beobachtungszeiten.

## Messung mit echten Serverdaten

Alte und neue SQL-Abfrage liefen in derselben lesenden PostgreSQL-Snapshot-
Transaktion. Die Zahlen sind kurze direkte Vergleichsmessungen einschließlich
Abruf/Umwandlung der SQL-Ergebnisse, keine langfristige Lastgarantie.

| Fall | Vorher | Optimiert |
| --- | ---: | ---: |
| Erste App-Seite, 1.000 Zeilen plus Prüfreihe | 9,424 s | 0,476 s |
| App-Seite ab einer Stunde zuvor | 5,973 s | 0,257 s |
| Fortsetzung der ersten App-Seite | 5,993 s | 0,150 s |
| Erste Platinum-Seite, 500 Zeilen plus Prüfreihe | 1,795 s | 0,465 s |
| Leere Seite mit zukünftigem Cursor, alle Waren | 11,370 s | 0,009 s |
| Unbekannte Ware ab einer Stunde zuvor | 0,257 s | 0,579 s |

Alle sechs Vergleiche lieferten identische vollständige Ergebniszeilen in
identischer Reihenfolge. Der erste Abruf einer unbekannten Ware war in dieser
Stichprobe langsamer; die unmittelbar folgende EXPLAIN-Messung benötigte
29 ms. Eine generelle Beschleunigung jeder möglichen Abfrage wird nicht
behauptet. Alle fünf geprüften optimierten EXPLAIN-Pläne schrieben null
temporäre Blöcke. Für die Fortsetzungsseite wurde kein eigener Planlauf erstellt.

Zusätzlicher Vorversuch für alle Waren ohne Filter: etwa 12–22 Sekunden vorher,
0,11–0,24 Sekunden optimiert, ebenfalls identische Ergebnisse. Diese Messungen
nutzten einen anderen Snapshot als die Tabelle oben.

## Prüfung

- 203 Servertests lokal und im Kandidaten-Image bestanden.
- 70 vorhandene App-Tests für Markt-Client, lokalen Bestand und Status bestanden.
- Isolierte PostgreSQL-17-Testdatenbank: 190 gezählte SQL-Vergleiche mit leeren
  Beständen, unbekannten Waren, fehlenden Metadaten, gleichen Zeitstempeln,
  ein-/mehrteiligen Warenfiltern und Seitengrößen bis 1.001.
- Vollständige Seitenläufe: 83 ALL-Seiten, drei Platinum-Seiten und sechs Seiten
  für Gold/Lithiumhydroxid; keine verlorenen oder wiederholten Zeilen.
- Station mit 1.205 Waren: Fortsetzung innerhalb derselben Station geprüft.
- Reine Stationsänderung und echter Endpoint-Cursor bestätigt.
- Synthetische Daten blieben ausschließlich in einer separaten, temporären
  Datenbank. Testcontainer und internes Testnetz anschließend entfernt.
- Nach Aktivierung zwei öffentliche HTTP-Seiten mit insgesamt 2.000 Zeilen,
  Reihenfolge und Cursor geprüft: etwa 0,53 s je Seite.
- Unveränderter echter App-Client lud weitere zwei 1.000-Zeilen-Pakete:
  0,451 und 0,386 s einschließlich Übertragung und Verarbeitung.
  Der persönliche lokale Marktbestand wurde dabei nicht beschrieben.

## Betrieb und Rückfall

Aktives Image: edframe-catalog-api:0.9.4-market-sync-20261012.
API-Version bleibt 0.9.4; öffentliche Schnittstelle und App bleiben kompatibel.

Nur der API-Container wurde ersetzt. Collector, PostgreSQL und Caddy behielten
Container, Images und Startzeiten. Der verifizierte Schema-Start verhinderte
wiederholte DDL. Während der Aktivierung wurden 566 zusätzliche EDDN-Nachrichten
verarbeitet; Fehlerzähler blieb bei 1. Der Collector wurde nicht angehalten.
Eine kurze Unterbrechung laufender API-Anfragen ist beim Containerwechsel möglich.

Sicherung einschließlich vorherigem API-Image und Quellen:
`/opt/edframe-deploy-backups/market-sync-20261012`.
Die Rückfall-Compose-Datei tauscht ausschließlich die API zurück.

Rohprotokolle und Helfer:
`outputs/market-sync-20261012` im Fortsetzungstask.

## Abschließende Live-Prüfung um 21:54 Uhr

Collector-Eingang 0,06 Sekunden alt, Fehlerzähler weiterhin 1. Seit der
Aktivierungsprüfung wurden weitere 4.964 Nachrichten verarbeitet. Der
Statistik-Snapshot wurde nach dem API-Wechsel automatisch erneuert und war
109 Sekunden alt. Alle Service-Identitäten entsprachen weiterhin dem Rollout.

Die 47 bisher erfassten Ausführungen der optimierten SQL-Varianten, einschließlich
der Vergleichsmessungen, zeigten keine temporären Schreibblöcke. Die mittleren
SQL-Zeiten je Variante lagen bei etwa 65–394 ms, das Maximum bei 571 ms.
Auch dieses kurze Messfenster ersetzt keinen Langzeitvergleich unter Spitzenlast.
