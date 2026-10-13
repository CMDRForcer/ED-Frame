# Collector-Wiederholungen und Abfragemessung am 12.10.2026

Die beauftragten Punkte 1 und 2 sind auf dem Server aktiviert. Die bestehende
App 1.0.9 und die öffentliche API bleiben kompatibel. Die Projektänderungen
bleiben lokal; es wurde kein weiterer App-Release oder Git-Push durchgeführt.

## Collector

Deadlocks und Serialisierungskonflikte werden nach vollständigem Rollback mit
identischer Nachricht und unveränderten Zeitstempeln erneut versucht. Maximal
vier Versuche und insgesamt höchstens 425 ms zusätzliche Wartepausen begrenzen
die Wiederholung. Datenbank- und Sperrwartezeit kommen dazu. Verarbeitete Daten
und Zähler werden erst beim erfolgreichen Commit veröffentlicht. Dauerhafte
Konflikte bleiben einmalig als Fehler sichtbar. Ungültige Daten, dauerhafte
SQL-Fehler und Verbindungsfehler mit unklarem Commit-Ergebnis werden nicht
blind erneut abgespielt.

Aktives Image: `edframe-catalog-collector:0.9.4-retry-20261012`.
Der neue Collector nutzt die bereits geprüfte Strukturkontrolle ohne
wiederholte Schema-DDL. Decoder, Projektionen und vorhandene Schreibfunktionen
wurden zwischen altem Collector und Image-Basis auf identische Hashes geprüft.

## Messung

`pg_stat_statements` ist vorgeladen und als Erweiterung installiert.
`track_io_timing` ist aktiv; SQL-Ausführungen werden auf oberster Ebene erfasst.
Planungsmessung bleibt deaktiviert. Der private Operatorbericht zeigt
Aufrufzahlen, Gesamt-/Durchschnitts-/Maximalzeit, gelesene Blöcke, temporäre
Schreibmengen und WAL-Mengen. SQL-Text wird nur mit der expliziten Option
`--sql` ausgegeben. Es gibt keinen neuen öffentlichen Diagnose-Endpunkt.

Das erste kurze Messfenster nach dem Neustart zeigte unter anderem 62
Outfitting-Snapshot-Schreibvorgänge mit insgesamt etwa 9,57 Sekunden und 154 ms
Durchschnitt. Das ist ein erster Hinweis für spätere Optimierungen, kein
repräsentativer Langzeitvergleich; nach einem Neustart ist der Datenbankcache
zunächst kalt. Fehlgeschlagene Abfragen werden weiterhin über Serviceprotokolle
analysiert, da das PostgreSQL-Modul erfolgreiche Ausführungen erfasst.

## Prüfung und Betrieb

- 198 Servertests lokal und im isolierten Kandidaten-Image bestanden.
- Separate PostgreSQL-17-Instanz: synthetische Transaktionsabbrüche mit echten
  SQLSTATEs `40P01` und `40001`; vollständiger Rollback, Erhalt der Zeitstempel
  und genau ein erfolgreicher Nachrichten-Zähler je Frame bestätigt.
- Anhaltender Konflikt: vier Versuche, bisherige Fakten erhalten, ein Fehler.
- Normalisierung und messbare Laufzeiten wiederholter SQL-Abfragen bestätigt.
- Testdatenbank und ausschließlich dafür angelegtes internes Testnetz entfernt;
  Produktion wurde für diese Tests nicht beschrieben.
- PostgreSQL-Neustart bis zur Bereitschaft: 10,915 Sekunden. Der Collector wurde
  dafür geordnet angehalten und anschließend ersetzt. Der Wechsel dauerte bis
  zum gestarteten Collector rund 12,3 Sekunden. In diesem kurzen Wartungsfenster
  war die EDDN-Aufnahme pausiert; eine vollständige Wiederzustellung des externen
  Live-Feeds lässt sich nicht garantieren.
- Nach dem neuen Collector-Start wurde tatsächlicher, aktueller Dateneingang
  separat bestätigt. Fehlerzähler blieb bei 1, keine neuen Collector-Logfehler.
- API und Caddy behielten Container-IDs und Startzeiten. PostgreSQL behielt
  Container, Image und Datenvolumen; die ursprünglichen Produkt-Tabellen-OIDs
  blieben identisch. Keine Produktdaten oder vorhandenen Indizes gelöscht.

Die initiale Rollout-Prüfung war bei der Wiederaufnahme zu großzügig und konnte
noch die letzte geordnet abgeschlossene Nachricht des alten Collectors sehen.
Eine zusätzliche Prüfung verglich den Eingang ausdrücklich mit der Startzeit
des neuen Containers und bestätigte laufenden Eingang. Der Hilfsskript-Check
wurde entsprechend präzisiert.

Sicherung und Rollback:
`/opt/edframe-deploy-backups/collector-observability-20261012`.
Gesichert wurden Quellen, altes Collector-Image, PostgreSQL-Konfiguration und
ein Schema-Dump. Es wurden weder Datenbankvolumen ausgetauscht noch
Dauerhaftigkeits-/Commit-Einstellungen gelockert.

Rohprotokolle und lokale Helfer:
`outputs/collector-retry-observability-20261012`.

## Abschließende Live-Prüfung um 21:33 Uhr

Health-Endpunkt: `ok`, API-Version 0.9.4. Letzte Collector-Nachricht etwa eine
Sekunde alt. Seit der zusätzlichen Startzeit-Prüfung kamen weitere 4.499
Nachrichten hinzu; der Fehlerzähler blieb unverändert bei 1. Die Statistik war
82 Sekunden alt und wurde nach dem Datenbank-Neustart bereits automatisch
erneuert. Der Operatorbericht lieferte 20 gemessene Abfragetypen mit ausgeblendeten
SQL-Texten im Standardmodus. Keine neue Messstatistik wurde manuell zurückgesetzt.
