# Server-Speicherbereinigung am 10.10.2026

Der ED-Frame-Server wurde im laufenden Betrieb von 92% auf 53% Plattenbelegung
entlastet. Die freie Reserve stieg von rund 3,54 GB auf 19,01 GB. Es wurden
keine Katalogdaten, Backups oder Rollback-Images gelöscht. API, Collector,
PostgreSQL und Caddy liefen mit denselben Container-IDs und Startzeiten weiter.
Die Angaben verwenden dezimale GB; der Datenbestand wurde während der Messung
weiter durch EDDN aktualisiert.

## Befund und Maßnahmen

Die Hauptursache waren zwei aufgeblähte B-Tree-Suchindizes. Ihre Definitionen
blieben beim einzelnen Neuaufbau mit `REINDEX INDEX CONCURRENTLY` identisch.
Die übrigen Indizes und alle Tabelleninhalte wurden erhalten.

| Index | Vorher | Direkt nach Neuaufbau | Freigegeben | Dauer |
|---|---:|---:|---:|---:|
| `markets_search_idx` | 6,745 GB | 0,344 GB | 6,402 GB | 27,4 s |
| `station_module_offers_search_idx` | 8,829 GB | 0,669 GB | 8,160 GB | 43,3 s |

Zusammen wurden 14,562 GB Indexplatz frei. Zusätzlich gab die Bereinigung
des mindestens 24 Stunden ungenutzten Docker-Buildcaches und der APT-
Paketarchive ungefähr 1 GB frei. Der aktuelle Buildcache von 618 MB blieb
erhalten. Die PostgreSQL-Datenbank sank von 23,534 GB auf 9,005 GB; WAL und
sonstige Dateien des Datenvolumes sind in dieser Datenbankgröße nicht enthalten.
Die abschließende Root-Filesystem-Messung um 13:57 UTC zeigte 21,396 GB belegt
und 19,012 GB verfügbar, also netto etwa 15,47 GB mehr Reserve als zu Beginn.

Vor dem Neuaufbau wurden beide Indexgrößen mit kleinen temporären Stichproben
abgeschätzt. Ein geprüftes Backup war vorhanden. Der Neuaufbau lief ohne
parallele Wartungsworker mit 128 MiB Wartungsspeicher und einem Platzwächter,
der bei weniger als 1,5 GB Reserve abgebrochen hätte. Die kleinste protokollierte
Reserve während des ersten Neuaufbaus lag über 4 GB.

Die beiden häufig aktualisierten Tabellen starten Autovacuum nun bei etwa 5%
toten Zeilenversionen plus 5.000 statt beim Standard von 20% plus 50.
Workerzahl, Speicher- und I/O-Kostenlimits wurden dafür nicht erhöht. Die
Einstellungen sind live angewendet und in der lokalen sowie serverseitigen
`schema.sql` hinterlegt. Frühere Bereinigung soll die Wiederverwendung
verbessern; sie garantiert keine dauerhaft konstante Indexgröße.

## Zusätzlicher Shared-Memory-Engpass

Bei der Abschlussprüfung scheiterte ein `/v1/status`-Abruf mit PostgreSQLs
`could not resize shared memory segment ... No space left on device`.
Betroffen war Docker-Shared-Memory mit einem Limit von 64 MiB, nicht die
inzwischen freie Platte. Der PostgreSQL-tmpfs wurde ohne Datenbankneustart
auf 256 MiB erweitert. `shm_size: 256m` ist in beiden Compose-Dateien für
künftige Container-Neuanlagen hinterlegt. Docker Inspect zeigt beim bestehenden
Container weiterhin die ursprüngliche HostConfig; `df /dev/shm` bestätigt die
wirksamen 268.435.456 Byte. Das gesamte Datenbank-RAM-Limit bleibt bei
1.258.291.200 Byte (1.200 MiB), und der tmpfs reserviert RAM erst bei Nutzung.

Die bisherigen Compose-/Schema-Dateien sind zusätzlich unter
`/opt/edframe-deploy-backups/storage-20261010` gesichert. Die erste
Namespace-Anpassung war wegen der Aufrufsyntax bzw. der Mount-Auflösung nicht
erfolgreich; der abschließende Aufruf mit explizitem tmpfs-Typ war erfolgreich.

## Prüfung und Grenzen

- 164 vorhandene Server-Tests bestanden mit den geänderten Quellen im
  isolierten Linux-Container, ohne Netzwerk oder produktive Datenvolumes.
- Alle sieben Indizes der beiden betroffenen Tabellen waren anschließend
  gültig und bereit; ihre Definitionen stimmten mit dem Ausgangszustand überein.
- Alle 37 zuvor inventarisierten Dump-/Quellarchive behielten Pfad, Größe und
  Änderungszeit. Die 14-Tage-Aufbewahrung wurde unverändert beibehalten.
- Das aktuelle Rollback-Backup wurde vollständig mit `pg_restore --file=/dev/null`
  gelesen. SHA-256:
  `24162f29a9c4be2d36c573cb65d26de8aecc34b5de069b4c02b122953a80238f`.
- Öffentliche Health-, Platinum- und Modulsuche sowie Serverstatus wurden über
  HTTPS geprüft. Beide Sucharten lieferten echte Ergebnisse; der Collector
  meldete weiterhin null Fehler. Platinum-/Modulsuche dauerten zuletzt etwa
  0,59/0,58 s, der Statistikabruf 41,93 s. Das sind einzelne Kontrollmessungen,
  kein Vorher-/Nachher-Performancebenchmark. Die Gesamtbestandsstatistik ist
  damit ein weiterer Ansatzpunkt für Caching.
- Keine App-Version wurde verändert. Schema, Compose, README und dieser Bericht
  werden gemeinsam mit dem nachfolgenden Statistikcache auf `main` veröffentlicht.

Die Rohmessungen und Einmalskripte liegen im Chat-Arbeitsordner unter
`outputs/server-storage-20261010`. Spätere Betriebskontrollen sollten Tabellen-
und Indexwachstum berücksichtigen; aus dieser kurzen Messung lässt sich keine
belastbare verbleibende Laufzeit der Reserve ableiten.

Technische Grundlage:
[PostgreSQL 17 REINDEX](https://www.postgresql.org/docs/17/sql-reindex.html),
[PostgreSQL-Wartung](https://www.postgresql.org/docs/17/routine-vacuuming.html),
[Tabellenspezifische Autovacuum-Parameter](https://www.postgresql.org/docs/17/sql-createtable.html#SQL-CREATETABLE-STORAGE-PARAMETERS),
[offizielles PostgreSQL-Docker-Image](https://hub.docker.com/_/postgres).
