# Paket 3 – günstige, transaktionale Regionsmarkierungen

**Nachtrag:** Die nachfolgende Umsetzung ersetzt den konfliktanfälligen
Start-/Endvergleich durch feste Ringseiten. Änderungen zwischen Seiten starten
die laufende Suche nicht mehr neu; die nächste Suche nutzt weiter aktuelle Zähler.
Details, Messergebnisse und Abwägungen in
[Stabile Mining-Ringseiten](mining_frozen_pages_2026-10-09.md).
Produktive Installation/Aktivierung bleibt weiterhin separat offen.

## Ergebnis und Stand

Die teure vollständige Inhaltsprüfung wurde im vorbereiteten API-Pfad durch
kleine regionale Änderungszähler ersetzt. Der reine 250-LY-Abgleich brauchte
im isolierten PostgreSQL-Test rund **1–3 ms statt 5,96 s**. Ein unveränderter
API-Abruf benötigte **28 ms**, ohne die Ringseiten erneut zu übertragen.
Das ist **nicht** die komplette Mining-Suchzeit einschließlich Internet,
Märkten, Powerplay, Routenberechnung oder GUI.

**Quellcode fertig und getestet; noch nicht produktiv installiert/aktiviert.**
Der laufende Server, Collector, produktive Katalog und bestehende AppData-Dateien
wurden nicht geändert. Das Protokoll bleibt standardmäßig ausgeschaltet. Eine
normale Aktualisierung installiert die Migration nicht heimlich.

## Funde und Fixes

- Vollständige JSON-/Ertragshistorien-Hashes waren bei großen Regionen zu teuer.
  Die API liest jetzt wenige **128-LY-Zellzähler** plus Referenz-Systemzähler.
  Die eigentliche Suche behält ihre exakte Kugelprüfung und alle Funktionen.
- Ein bloßer Inhaltsvergleich konnte ein Einfügen und anschließendes Löschen
  zwischen Seiten übersehen. Die neuen Zähler und historischen Positionszellen
  bleiben erhalten und erkennen auch diese kurzzeitigen Änderungen.
- 20 PostgreSQL-Statement-Trigger decken Einfügen, Ändern, Löschen und TRUNCATE
  von Ringdaten, beiden Ertragstabellen, Ring-Zusatzdaten und relevanten
  Referenz-Systempositionen ab. Daten und Zähler werden **gemeinsam committed**.
- Alte und neue Namen/Positionen werden berücksichtigt; Änderungen an
  gleichnamigen Metadaten außerhalb der Suchkugel bleiben sichtbar.
- Unbekannte Positionen invalidieren konservativ. Unbeteiligte Systemupdates
  und ignorierte Duplikate lösen keinen unnötigen Zählerwechsel aus.
- Eine indizierte Altersgrenze erkennt auslaufende Beobachtungen auch ohne
  Schreibvorgang. Die erste Fassung sortierte versehentlich formatierte
  Zeitstempel: `ORDER BY age.observed_at` erzwingt die Original-Zeitspalte und
  vermeidet das Formatieren/Sortieren von über einer Million Zeilen.
- Ein räumlicher Index über stark wiederholte Systemzellen war beim großen
  Import zu teuer. Die verworfenen Varianten wurden durch wenige Zellzähler
  mit B-Tree-Schlüssel ersetzt; historische Systemzellen brauchen keinen
  zusätzlichen räumlichen Index mehr.
- Nicht vorhandene/unfertige Marker oder unregistrierte neue Referenznamen
  erlauben keine Cache-Bestätigung: HTTP 503, frische kompatible Client-Seiten,
  **kein Rückfall auf den teuren Inhalts-Hash**.
- DB-Generation und Code-/Referenzversion schützen gegen Versionswechsel.
  Nach einem Datenbank-Restore ist eine explizite Generationsrotation Pflicht.
- BGS-Prognosen, Preis-/Merit-Berechnungen und Quell-Zeitstempel bleiben unverändert.

## Messungen

Temporärer, isolierter PostgreSQL-Testbereich mit **1.040.960 kopierten öffentlichen
Ringdatensätzen, vollständigen Ringspalten und Indizes**. Keine produktiven
Schreibvorgänge. Ertrags-/Referenz-Zusatzdaten sind dort synthetische Testdaten,
kein vollständiger Klon aller Serverdaten. Variable Serverlast, sequentielle
Stichproben, keine allgemeine Kaltstart- oder Netzwerk-Benchmark-Garantie.

| Radius | Alte Inhaltsprüfung, ein Lauf | Neuer Zählerabgleich, vier Läufe |
| --- | ---: | --- |
| 50 LY | 0,205 s | 13,9 / 2,0 / 1,6 / 1,4 ms |
| 250 LY | 5,964 s | 3,3 / 2,1 / 1,4 / 1,5 ms |
| 500 LY | 8,428 s | 18,9 / 2,9 / 2,9 / 2,1 ms |

Isolierter API-Smoketest: **25.230 Ringe über sechs Seiten, exakt gleiche
Inhalte und Reihenfolge**. Normaler Handler 5,26 s; Marker-Handler 4,16 s.
Der zweite Lauf profitiert möglicherweise von Warmdaten: daraus wird **kein
pauschaler Erstsuche-Gewinn** abgeleitet. Unveränderte Bestätigung: 0,028 s.
Ein tatsächlich eingefügter und wieder gelöschter Ring zwischen Seiten wird
mit HTTP 409 korrekt abgewiesen, statt als vollständiger Snapshot gespeichert.

Schreibkosten, 200 einzelne Änderungen in einer Transaktion: ohne Trigger
0,118 s, mit Triggern 0,247 s, also in dieser Stichprobe rund **0,65 ms zusätzlich
je Änderung**. 1.000 Änderungen als eine Anweisung mit Triggern: 0,519 s.
Das ist kein vollständiger Collector-Durchsatztest unter Dauerlast.

Fünf Marker-Tabellen einschließlich Indizes: **41.705.472 Byte, etwa 39,8 MiB**.
Einmaliger Aufbau der Marker im Test: 38,7 s. Gegenüber den Quelldaten klein;
keine zusätzliche Gigabyte-Datei auf dem Windows-PC.

## Prüfung

- **1.235 App-Tests grün**, einschließlich vorhandener QML-/Interaktionsprüfungen.
  TEMP/TMP/LOCALAPPDATA waren auf einen eigenen Testbereich umgeleitet.
- **119 Server-Unit-Tests grün**.
- **33 echte PostgreSQL-Integritätsprüfungen grün**: u. a. Änderungen/Löschungen,
  FK-Kaskaden, Bewegungen/Namenswechsel, Duplikate, Ablauf ohne Mutation,
  Rollback einer fehlgeschlagenen Migration, Repeatable Read und parallele
  Commits verschiedener Systeme in derselben Zelle.
- Zusätzlicher vollständiger Paging-Test mit kurzzeitiger Mutation bestanden.
- Syntaxprüfung der geänderten/neuen Python-Dateien, Repository-Hygiene und
  `git diff --check` bestanden.
- Sämtliche verwendeten temporären Server-Testschemata wurden entfernt;
  Originaldaten, laufende Dienste und installierte Serverquellen bleiben erhalten.

Messprotokolle im ignorierten Testbereich:
`.test-tmp/mining-epochs-20261009-01/postgres-final.jsonl`,
`postgres-integrity.jsonl`, `app-tests.log`, `server-tests.log`.

## Rollout und verbleibende Grenze

### Bedingte Freigabe – Live-Prüfung am 09.10.2026

Der Nutzer erlaubt den Rollout nur ohne Nachteile. Diese Voraussetzung ist
derzeit nicht erfüllt; deshalb **keine produktive Installation oder Aktivierung**.
Die folgende Prüfung war ausschließlich lesend, mit vier Sekunden SQL-Timeout.

In den für die Beispielregion (250 LY um die bisherigen Benchmark-Koordinaten)
konservativ ausgewählten Zellen lagen 286.145 Ringe. **Vier** davon wurden in
den letzten fünf Sekunden empfangen/aktualisiert, **acht** in 15 Sekunden und
**40** in 60 Sekunden. Das zählt zuletzt geänderte Zeilen, nicht sämtliche
Ereignisse, und ist eine einzelne Live-Stichprobe. Die Zähler würden diese
Änderungen während einer mehrseitigen Suche korrekt erkennen; damit drohen
zusätzliche Seiten-Neustarts trotz schneller Einzelprüfung.

Zusätzlich bleiben gemessener Trigger-Schreibaufwand, circa 40 MiB
Server-Marker und ein kurzes Wartungsfenster. Eine Installation bei weiterhin
ausgeschaltetem Protokoll würde bereits Schreibaufwand verursachen, ohne die
App-Abfragen zu beschleunigen. Daher kein verdeckter Vorab-Rollout.

Server-Stichprobe: etwa 10,9 GiB frei; API 302,8 MiB, Collector 43,9 MiB;
PostgreSQL 1,035 GiB einschließlich Cache bei 1,172-GiB-Containerlimit und
66,5 % CPU in der Momentaufnahme. Das allein beweist keine Überlastung.
Collector meldet null Verarbeitungsfehler. Öffentliche Marker-Tabelle weiterhin
nicht vorhanden. Bestehende Dienste und Katalogdaten bleiben unverändert.

Empfohlene Voraussetzung für den Rollout: **stabile, begrenzte serverseitige
Such-Snapshots** für alle Ergebnisseiten einer Suche. Neue Meldungen bleiben
gespeichert und werden beim nächsten Abgleich berücksichtigt; Beobachtungen
werden dabei nicht künstlich frisch gemacht. Auch dieses Verfahren braucht
begrenzten Server-Speicher und Last-/Gleichheitstests, keine Nullkosten-Garantie.

Für die produktive Installation werden **fünf additive Zählertabellen und
20 Trigger** benötigt. Zuerst geprüfte Datenbanksicherung und kurze Wartung,
dann `python -m edframe_catalog.mining_epochs --install`; bestehende
Katalogdatensätze werden nicht gelöscht. Freigabe für diese konkrete Migration
und Dienstaktualisierung steht noch aus. Anleitung im Server-README.

Wichtig: Günstige Zähler machen geänderte Daten nicht unverändert. Während
einer mehrseitigen Suche eintreffende relevante Live-Änderungen erzwingen
weiterhin einen Neustart oder ausdrücklich provisorische, nicht cachebare
Ergebnisse. Auch Randzellen/fehlende Positionen können konservativ invalidieren.
Vor einer allgemeinen Aktivierung sind Collector-Dauerlast und Häufigkeit
dieser Paging-Konflikte zu prüfen. Falls Konflikte oft auftreten, ist der
nächste Hebel **stabile serverseitige Ergebnisseiten aus einem Such-Snapshot**,
nicht das Ignorieren von Änderungen oder Aufweichen der Aktualitätsregeln.
