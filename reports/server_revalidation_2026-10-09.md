# Paket 3: Server-Abgleich – Kostenprüfung und sichere Optimierungen

Nachtrag: Die unten beschriebene teure Inhaltsprüfung wurde anschließend im
vorbereiteten API-Pfad durch transaktionale Zellzähler ersetzt. Aktueller Stand
und Tests: [Regionale Änderungszähler](mining_region_epochs_2026-10-09.md).
Auch diese Fortsetzung ist noch nicht produktiv installiert/aktiviert.

## Ergebnis

Die App entpackt alte Regionsdaten nicht mehr vorsorglich. Sie liest zunächst
nur den Revisionsschlüssel und lädt den prüfsummengeschützten Inhalt erst nach
einer unveränderten Serverantwort. Geänderte Regionen überspringen diese alte
JSON-Kopie vollständig. Bei beschädigtem, zwischenzeitlich entferntem oder
ersetztem Cache wird frisch nachgeladen, niemals ungeprüft wiederverwendet.

Das vorbereitete Serververfahren ist jetzt **auch im Code standardmäßig
deaktiviert**, damit es bei einem späteren anderen Deployment nicht unbemerkt
aktiv wird. Deaktivierte Protokoll-Anfragen einschließlich Folgeseiten erhalten
normale frische regionale Seiten, ohne Hashkosten oder erzwungenen Neustart.

Die Server-Revisionsabfrage wurde optimiert, **nicht deployt**. Der laufende
Server unterstützt größere regionale Seiten, aber noch kein Snapshot-Protokoll.
Darum ist dies keine Beschleunigung der bereits installierten Windows-Version.

Die allgemeine Aktivierung bleibt offen: Unveränderte Wiederholungssuchen
profitieren, neue/geänderte große Regionen bekommen weiterhin teure zusätzliche
Inhaltsprüfungen. Eine globale Aktivierung wäre derzeit kein Erstsuche-Fix.

## Funde und Änderungen

- Die ursprüngliche Serverabfrage schätzte einen dynamischen Systemnamen-Satz
  stark zu klein ein. Tatsächlich umfasst die 250-LY-Prüfung etwa 144.000
  Datensätze/27.000 Systeme, nicht nur die etwa 25.000 passenden Ringe.
- Systemnamen und Regions-Mitgliedschaft werden jetzt zuerst ermittelt. Die
  vollständige Inhaltsabfrage bekommt diese konkreten Namen als Parameter,
  weiterhin in **derselben READ-ONLY/REPEATABLE-READ-Transaktion**.
- Bis 100 LY nutzt die Mitgliedschaft den bereits vorhandenen räumlichen Index
  plus die unveränderte exakte Kugelprüfung. Größere Regionen behalten den
  günstigeren vollständigen Kugelscan. Die Grenze ist eine konservative
  Zugriffsweg-Wahl, keine veränderte Suchreichweite.
- Versuche mit pauschalem Box-Index, expliziten Joins und einer engeren
  Commodity-Auswahl wurden verworfen: größere Regionen wurden langsamer;
  eine engere Auswahl würde außerdem die konservative Änderungsprüfung schwächen.
- Kein Wechsel auf nur Anzahl, jüngsten Zeitstempel oder ungeprüfte TTL.
  Mitgliedschaft, Löschungen, vollständige Datensätze, beide Ertragstabellen,
  gleichnamige System-/Ring-Zusatzdaten außerhalb der Kugel, Referenzpositionen
  und Code-/Grundbestandsversionen bleiben im Fingerprint.
- BGS, Preis-/Merit-Berechnungen und Quell-Zeitstempel bleiben unverändert.
  Bestehende Profile, Historien und Katalogdateien wurden nicht verändert.

## Messungen

Isolierter synthetischer Client-Test: 24.447 Ringe, identischer Eingabe-Hash,
echte Projektion/SQLite/Kompression, fünf Wiederholungen; **ohne HTTP, SQL und GUI**.

| Client-Verarbeitung | Vorher, Median | Nachher, Median |
| --- | ---: | ---: |
| Geänderte Region | 0,650 s | 0,403 s |
| Unveränderte Region | 0,186 s | 0,185 s |
| Alte Payload bei geänderter Region entpackt | 1-mal | 0-mal |

Rund **38 % weniger lokale Verarbeitung bei geänderten Regionen**. Unveränderte
Regionen behalten eine Bestätigung, geänderte fünf simulierte Seiten. Alle
Ringe, geänderten Inhalte und Beobachtungszeiten stimmen überein. Die repetitive
Fixture ist keine Vorhersage für Dateigröße, RAM oder reale Gesamtsuchzeit.

Alte/neue Server-SQL wurden ephemer im eigenen API-Container ausgeführt, ohne
Quellinstallation, Route oder Neustart; begrenzte READ-ONLY-Transaktionen mit
15 Sekunden Statement-Timeout. Alte und neue Revisionswerte waren **identisch**:

| Radius | Alte Inhaltsprüfung | Neue Inhaltsprüfung |
| --- | ---: | ---: |
| 50 LY, zwei Läufe | 1,306 / 0,979 s | 0,351 / 0,095 s |
| 250 LY, zwei Läufe | 6,308 / 6,199 s | 5,493 / 6,063 s |
| 500 LY, ein Lauf | 14,057 s | 11,469 s |

Variable Serverlast, sequentielle Stichproben; kein umfassender Kalt-/Warm-Test.
Ein früher verworfener Box-Versuch erreichte bei 500 LY das Diagnose-Timeout;
er wurde nicht installiert. Der deutliche kleine-Regionsgewinn lässt sich nicht
pauschal auf 250/500 LY übertragen.

Vollständiger Handler-Vergleich mit dem deployten Server, **ein gemeinsamer
Datenbanksnapshot**, identische Reihenfolge und Inhalte jeder Seite:

| Region | Inhalt | Normale Seiten | Mit Revisionsprüfung | Unverändert bestätigt |
| --- | --- | ---: | ---: | ---: |
| 50 LY | 287 Ringe, 0 Referenzen | 1 / 0,965 s | 1 / 0,631 s | 1 Anfrage / 0,155 s |
| 250 LY | 25.382 Ringe, 25 Referenzen | 6 / 15,770 s | 6 / 27,692 s | 1 Anfrage / 4,960 s |

Die unveränderte Antwort überträgt **keine Ring-/Referenzzeilen**. Sie bestätigt
nur den alten Inhalt, erzeugt keine neue Sichtung und verlängert dessen Alter
nicht. Ein geänderter/fehlender großer Snapshot kostet dagegen zwei zusätzliche
vollständige Prüfungen. Die Zahlen sind In-Process-Handler/SQL-Zeiten, **keine
installierten App-/Internet-Zeiten**. Ring-Rebase/History und frische Markt-/
Powerplay-Abfragen sind darin nicht enthalten. Es gibt keinen Zeilen-Delta-Stream.

## Grenzen und nächster Server-Schritt

Vor einem allgemeinen Rollout braucht es günstige, **transaktional gepflegte
regionale Änderungsmarkierungen**, einschließlich Inserts/Updates/Deletes,
Positionswechseln, Ertragsdaten und Referenz-/Fallback-Abhängigkeiten. Dafür
ist eine gesondert geprüfte Schema-/Collector-Änderung mit Deployment-Freigabe
nötig; keine ungefragte Produktionsmigration in diesem Paket.

Die unveränderten Start-/End-Inhaltsprüfungen erkennen Änderungen vorhandener
Zeilen auch bei Rückänderung durch ihre Versionskennung. Sie sind aber kein
über alle HTTP-Seiten gehaltener Datenbanksnapshot: eine vorübergehend neu
eingefügte und wieder entfernte Zeile kann beide Inhaltsprüfungen umgehen.
Dieser bestehende Protokoll-Grenzfall gehört ebenfalls in die transaktionale
Revisionslösung vor einem pauschalen Rollout. **Alle geprüften Seiten im
Vergleichssnapshot waren identisch; das beweist keine beliebige Live-Mutation.**

PostgreSQL dokumentiert die Zeilenversionskennung und deren langfristige
32-Bit-Grenze unter [System Columns](https://www.postgresql.org/docs/17/ddl-system-columns.html).
Deshalb wurde kein vermeintlich billiger Alleinbeweis aus `xmin` eingeführt;
die vollständigen Inhaltschecks bleiben erhalten.

## Prüfung und Reproduktion

- **1.235 App-Tests grün**, einschließlich vollständigem nativen QML-Smoke.
- **111 Server-Tests grün**; zehn zusätzliche Client-/Server-Vertragstests.
- Defekter/fehlender/ausgetauschter Cache, querygebundene Schlüssel, frische
  Rückfallebene, erwartete Revision, vollständige Zusatzdaten und kleine/große
  SQL-Zugriffswege getestet; unveränderte alte Vertragsprüfungen weiter grün.
- `git diff --check` und Repository-Hygiene bestanden.
- Kein Commit/Push/Release, Deployment, Neustart, DDL oder Datenbank-Schreibzugriff.
  Änderungen aus Paket 1/2 unverändert erhalten.

Werkzeuge: `tools/benchmark_mining_revalidation.py` (optional `--baseline`),
`server/catalog_service/ops/verify-mining-revision-cost.py`,
`server/catalog_service/ops/verify-mining-revision-handler.py`.

Mess-JSONs, verworfene Varianten und Testlogs bleiben unter
`.test-tmp/server-revision-20261009-01/`. Die App-Tests schrieben ausschließlich
in ein isoliertes Testprofil, nie in das vorhandene Benutzerprofil.
