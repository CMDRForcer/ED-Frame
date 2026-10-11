# Speicher zurückgewonnen, Katalog und Suchfunktionen erhalten
11. Oktober 2026 · ausgeführt um 20:08–20:10 Uhr MESZ

Die vom Benutzer gewünschte Speicherbereinigung hat **5,205 GB Indexplatz**
zurückgewonnen. Alle Werte verwenden dezimale GB. Katalogdaten wurden durch
diese Wartung weder gelöscht noch hinsichtlich ihrer Aufbewahrung verändert.
Die Datenbank einschließlich ihrer Indizes sank von etwa 15,29 auf 10,13 GB.

## Messung und Durchführung

Die zwei häufig aktualisierten Suchindizes belegten vorab 6,34 GB. Kleine
temporäre Stichproben mit zusammen rund 49.000 Zeilen schätzten einen kompakten
Stand auf 1,154 GB. Nur diese temporären Tabellen wurden angelegt; ihre
Transaktionen wurden zurückgerollt. Produktionszeilen wurden nicht verändert.

Die bestehenden Indizes wurden danach einzeln mit
`REINDEX INDEX CONCURRENTLY` neu aufgebaut. Definitionen, Sortierung und
Suchmöglichkeiten bleiben identisch. PostgreSQL erlaubt dabei weiter normale
Lese- und Schreibzugriffe; der Neuaufbau benötigt zusätzliche Arbeit und
vorübergehenden Platz. [PostgreSQL 17: REINDEX](https://www.postgresql.org/docs/17/sql-reindex.html).

| Index | Vorher | Direkt danach | Zurückgewonnen | Dauer |
|---|---:|---:|---:|---:|
| `markets_search_idx` | 2,576 GB | 0,394 GB | 2,182 GB | 36,485 s |
| `station_module_offers_search_idx` | 3,779 GB | 0,756 GB | 3,023 GB | 45,319 s |

Freier Platz stieg von 11,58 auf rund **16,99 GB**. Die Plattenbelegung sank
von **71,3 % auf 57,9 %**. Die Netto-Plattenänderung unterscheidet sich vom
exakt gemessenen Indexgewinn, da Collector und PostgreSQL-WAL weiterlaufen.

Vorher wurde das tägliche Backup vom 11.10.2026, 04:00 UTC vollständig durch
`pg_restore --file=/dev/null` gelesen. Es enthält 405.253.451 Byte; SHA256:
`0f5f2ccd083ea8635dd89529091a77b7a77cead9071714eaed485590045ac1bc`.
Das ist eine vollständige Archiv-Leseprüfung, kein Wiederherstellungstest.

Die Wartung verwendete 128 MB Wartungsspeicher, keine parallelen
Wartungsworker, eine gemeinsame Wartungssperre, fünf Sekunden Lock-Limit
und acht Minuten Statement-Limit je Neuaufbau. Ein Wächter prüfte alle fünf
Sekunden freien Platz und Fortschritt; unter vier GB Reserve hätte er den
eigenen Neuaufbau abgebrochen. Die niedrigste protokollierte Reserve während
der Neuaufbauten lag bei rund 11,14 GB.

## Funktions- und Leistungskontrollen

- Alle sieben Indizes der beiden Tabellen sind gültig und einsatzbereit.
  Ihre Definitionen stimmen mit dem Stand vor der Wartung überein.
- API, Collector, PostgreSQL und Caddy haben unveränderte Container-IDs
  und Startzeiten. Der Collector empfängt weiter, Fehlerzähler unverändert 0.
- Alle 26 inventarisierten Datenbank-Backups behalten Größe und Änderungszeit.
  Backup-Aufbewahrung, Quellarchive und Rollback-Images wurden nicht angefasst.
- Healthcheck, Platinum- und Modulsuche sowie Statistik bestehen vor,
  während und nach der Wartung. Beide Suchabfragen liefern jeweils drei Ergebnisse.
- Vorherige Einzelabrufe: Markt 0,745 s, Modul 0,753 s. Während der zweiten
  Indexwartung: 0,639/0,843 s. Die ersten Nachabrufe lagen bei 1,802/2,021 s.
  Die anschließenden drei Kontrollen pro Suchart ergaben 0,129–0,610 s
  beziehungsweise 0,119–0,710 s. Der Statistikcache war wieder frisch.

Die anschließenden Kontrollen zeigen keinen anhaltenden Leistungseinbruch.
Kalte Index-/Plattencaches und gleichzeitig laufende Statistikberechnung
kommen als Erklärung der ersten langsameren Abrufe infrage; ihr jeweiliger
Anteil wurde nicht separat gemessen. Diese wenigen Abrufe sind kein allgemeiner
Lastbenchmark und belegen keine feste Beschleunigung aller App-Funktionen.

## Weiterer Hebel

Beide Tabellen haben seit dem Beginn ihrer PostgreSQL-Statistik jeweils über
100 Millionen Updates erhalten. Beobachtungszeiten sind Teil der Suchindizes;
auch notwendige reine Aktualitätsänderungen erzeugen neue Indexeinträge.
Normale Vacuum-Wartung kann vorhandenen Platz wiederverwenden, gibt aufgeblähte
Indizes aber nicht zuverlässig in dieser Größenordnung an die Platte zurück.
[PostgreSQL 17: Routine Vacuuming](https://www.postgresql.org/docs/17/routine-vacuuming.html).

Der nächste dauerhafte Ansatz ist weniger Schreibarbeit für unveränderte
Meldungen und die getrennte Behandlung von Aktualitäts- und Angebotsänderungen.
Das erfordert einen eigenen Vergleich von Merge-Verhalten, Synchronisierung,
Abfrageplänen und Last. Neue Zeitstempel dürfen dabei nicht einfach verworfen
werden. Diese Einmalwartung ändert weder Collector-Logik noch Indexdefinitionen
oder automatische Wartungszeitpläne; erneutes Wachstum bleibt möglich.

Kein App-Build, Commit, Push oder Release. Serverseitiger Wartungsnachweis:
`/opt/edframe-deploy-backups/storage-compaction-20261011/record.json`.
Rohmessungen und Kontrollabfragen: `outputs/server-storage-20261011` (lokales Prüfartefakt).
