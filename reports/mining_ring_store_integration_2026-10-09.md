# Ringspeicher integriert und echter Bestand übernommen

Stand: 9. Oktober 2026. Lokaler Windows-Build **1.5.44**. Die native App
verwendet den regionalen SQLite-Ringspeicher jetzt standardmäßig.

Der aktuelle echte Bestand wurde vollständig übernommen: **391.214 Ringe**.
Der eingefrorene Vergleichsbestand enthielt noch 391.212; die inzwischen
hinzugekommenen Datensätze sind ebenfalls enthalten. Original-JSONs und die
bestehende Historien-Datenbank wurden weder überschrieben noch gelöscht.
Ihre Prüfsummen sind nach der Übernahme unverändert. BGS-Prognosen wurden
nicht verändert. Die frühere installierte EXE wurde nicht überschrieben;
der neue portable Build wird separat bereitgestellt. Kein Serverdeployment,
Push, Release-Tag oder öffentliches GitHub-Release gehört zu diesem Durchgang.

## Produktive Integration

- Vollständige, unkomprimierte JSON-Payloads in versionierten SQLite-Fakten.
  Quellreihenfolge, Beobachtungszeiten, unbekannte Felder und Root-Metadaten
  bleiben erhalten. Die ursprüngliche JSON-Datei bleibt zusätzlich bestehen.
- RTree und System-/Identitätsindizes für regionale Abfragen, freie
  Startsysteme und gezielte Änderungen. Es gilt weiter die bisherige, auf
  0,1 LY gerundete inklusive Radiusgrenze. Fehlende/nichtendliche Koordinaten
  werden entsprechend den vorhandenen Regeln behandelt. Keine Abfrage wird
  wegen eines Cachelimits abgeschnitten.
- Höchstens ein regionaler Cache je View, begrenzt auf 130.000 Zeilen und
  128 MiB Payload; größere Regionen werden vollständig gestreamt. Der
  SQLite-Page-Cache beträgt 4 MiB. Gemeinsame Feldnamen/Faktentexte und interne
  Array-Snapshots erhalten die sparsame Katalogdarstellung. Keine globale
  Ringliste oder globale Ring-Identitätsmap beim Laden oder Suchen.
- Lokale Journal-Ergänzungen werden gegen ihre indizierten Zielringe
  zusammengeführt. Unveränderte regionale Zeilen werden weder tief kopiert
  noch erneut serialisiert. Systemvorschläge, Commodity-Auswahl und
  Datenqualität bleiben verfügbar, ohne sämtliche Payloads in RAM zu laden.
- Neue Beobachtungen, verdrängte Fakten und ein Historien-Outbox-Eintrag werden
  gemeinsam atomar committed. Ein Fehler des vorhandenen Historienarchivs
  lässt die Outbox bestehen; späteres Archivieren bestätigt nur exakt die
  gespeicherte Payload. Alte Faktversionen bleiben unabhängig davon erhalten.
  Der Historienexport nimmt aktive Ringdaten und ausstehende Archivdaten mit.
- Unveränderliche Reader bleiben an ihre Datenbank und Revision gebunden.
  Schreibvorgänge und Qt-Publikation prüfen Profil, Datenbank, Revision und
  Reset-Generation. Batch-Belege verhindern doppelte Übernahme beim Shutdown,
  wenn ein Worker bereits committed hat und sein Qt-Signal noch aussteht.
- Der explizite Ring-Reset archiviert/markiert Versionen im Worker, erhält das
  ursprüngliche JSON und verhindert dessen erneutes Einspielen nach Neustart.
  Anstehende Beobachtungen werden vorher verarbeitet; während des Resets
  eingehende Daten bleiben erhalten. Profilwechsel warten auf den Ring-Reset.
- Alte Identitätsformate werden mit dem vorhandenen Domain-Merger einmalig
  normalisiert; die rohen Originalversionen bleiben auf Platte. Änderungen
  aus einer später geschriebenen Legacy-Datei werden ergänzend übernommen,
  ohne SQLite-only-Fakten zu entfernen. Unveränderte/reihenweise verschobene
  Payloads werden nicht erneut als neue Beobachtung eingespielt.

Frische, Ertrag, Filter, Ranking, Preise, Nachfrage und Powerplay-Eignung laufen
weiter im vorhandenen Domain-Code. Der Speicher erzeugt keine Verifizierung.

## Übernahme des echten Bestands

Das separate Werkzeug `tools/adopt_mining_ring_catalog.py` startet weder den
Controller noch HTTP oder Uploads. Es schreibt ausschließlich die neue
Ring-Datenbank im ausdrücklich beauftragten Profil. Ein Aufbau wird erst nach
vollständiger Transaktion und erneuter Quellprüfung atomar verfügbar.
Vorhandene Ziele werden nicht überschrieben, fehlerhafte Quellen nicht durch
leere Daten ersetzt. Abgebrochene Staging-Dateien werden entfernt.

Ergebnis: 391.214 vollständige Payloads in identischer Reihenfolge,
Root-Metadaten gleich, SQLite `integrity_check` und RTree `rtreecheck` jeweils
`ok`. Payload-/Reihenfolge-SHA256:
`d51f96f33f21fc0b2c38fc18c6b124cf114827a1c80492d72d92f9d3d32ad8ea`.

Übernahmezeit: 27,62 s. Neue Datenbank: 676.139.008 Byte, rund **644,8 MiB**,
zusätzlich zum erhaltenen JSON. Die bestehende Historien-Datenbank wird
weiterverwendet; sie wurde nicht kopiert oder umgebaut. Der separate
Übernahmebericht enthält die Vorher-/Nachher-Prüfsummen der fünf geprüften
Originaldateien. Kein Profilname oder Journal-Inhalt wurde exportiert.

## Verifikation

**1.271 Unit-/Vertragstests grün**, einschließlich 24 neuer produktiver
Ringstore-/Controller-Tests. Nach der abschließenden defensiven Behandlung
fehlerhafter Ressourcen-Zählwerte zusätzlich alle 24 Store-Tests grün.
Die Korrektur betrifft keine Zeile des tatsächlich übernommenen Bestands.

Abgedeckt sind atomare Übernahme und Rollback, vollständige Payloads,
Unicode/BOM/Chunkgrenzen, alte Identitäten, Änderungen der Quelle,
Historiensicherung/Retry, doppelte Shutdown-Belege, unabhängige Reader,
Profil-/Datenbank-/Revisions-/Reset-Fences, verzögerte Publikation,
Radiusgrenzen, fehlende/NaN-Koordinaten, Cacheüberschreitung ohne Trunkierung,
lokale Ergänzungen mit verschobenen Koordinaten, dynamische Datenqualität und
kein globaler Payload-Lauf für Commodity-/Qualitätsanzeigen.

Der produktive Store wurde außerdem vollständig gegen die eingefrorene
391.212-Ring-Datei geprüft. Alle Payloads, Metadaten und deren Reihenfolge
stimmen. Sieben Filterkombinationen und jeweils 100 vollständige Routen für
REINFORCE, ACQUIRE und HIGHEST PROFIT liefern bei 250 und 500 LY dieselben
Ergebnis-Hashes wie der JSON-Pfad. Auch Recheck/ACQUIRE bei um zwei Tage
fortgeschrittener Uhr stimmen. Eingaben und Prototyp-Datenbank unverändert.

Native Quelle und Windows-Paket: jeweils **33 Smoke-Bereiche bestanden**,
einschließlich MiningFinder, Profilfunktionen, Dialogen und QML-Diagnostik.
Isolierte Laufzeitverzeichnisse und synthetisches Journal; kein Start des
Controllers auf dem echten Benutzerprofil für Tests. Syntax-, Whitespace-
und Repository-Hygieneprüfungen bestanden.

## Messungen und praktische Grenzen

Produktiver Offline-Replay, je ein frischer Prozess pro Variante und Radius.
Kein Median und keine Zusage für einen kalten Datenträger oder Live-HTTP:

| Messpunkt | JSON 250 LY | SQLite 250 LY | JSON 500 LY | SQLite 500 LY |
| --- | ---: | ---: | ---: | ---: |
| Ringzugriff einschließlich Region | 5,86 s | 1,64 s | 5,76 s | 2,66 s |
| RAM nach Ringzugriff | 433,5 MiB | 137,2 MiB | 433,9 MiB | 211,3 MiB |
| RAM nach kompletter Vergleichsmatrix | 619,6 MiB | 319,0 MiB | 641,1 MiB | 413,1 MiB |

Native Qt/QML-App aus Quelle, Offscreen-/Software-Rendering, gleicher
öffentlicher Testbestand, gesperrtes HTTP und leerer isolierter Marktstore:

- Erste Oberfläche nach 1,31–1,37 s. Operations lädt keinen globalen Ringbestand.
- Erstmaliger Aufbau plus Mining-Laden: 35,59 s im Hintergrund. Nach fertiger
  Übernahme: **2,06–2,09 s** bis zum geladenen MiningFinder.
- RAM nach Mining-Laden: **228,5–228,9 MiB**. Nach 250-LY-Planung: 389,6 MiB;
  nach 500-LY-Planung mit zusätzlicher synthetischer lokaler Beobachtung:
  481,1 MiB. Powerplaydateien laufen weiter über ihre bisherigen Loader.
- Regionen vollständig: 53.545 beziehungsweise 120.158 Ringe, letztere inklusive
  der künstlichen lokalen Testergänzung. Größter Qt-Timerabstand während Mining
  einschließlich Planung: 60 beziehungsweise 92 ms, kein Abstand über 100 ms.

Die frühere native Messung mit globalem JSON lag bei 613,7 MiB nach Mining-Laden;
sie hatte einen etwas älteren Powerplaybestand und ist kein streng identischer
Vorher-/Nachher-Vergleich. Breite ALL-COMMODITIES-Berechnungen brauchen weiterhin
mehr Zeit. Der neue Ringspeicher beschleunigt nicht jeden verbleibenden Markt-,
Netzwerk- oder Powerplay-Schritt. Abschließende Sicherung größerer noch laufender
Beobachtungsbatches kann das Schließen verlängern.

## Reproduzierbare lokale Artefakte

- `.test-tmp/ring-production-20261009/result.json`: integrierter Offline-Vergleich.
- `.test-tmp/ring-native-20261009/restart.log`: Neustart und 250-LY-Plan.
- `.test-tmp/ring-native-20261009/delta-500.json`: echte QML-Pipeline mit lokalem Delta.
- `.test-tmp/ring-integration-20261009/final-all-tests.log`: vollständige Tests.
- `.test-tmp/ring-build-final-20261009/final-build.log`: finale Windows-Paketierung.

Der portable Windows-Build enthält keine Benutzerdateien oder Ring-Datenbank.
Er nutzt beim normalen Start das vorhandene Profil und dessen bereits
übernommenen Ringspeicher. Den kompletten Programmordner einschließlich
`_internal` verwenden. Die bisherige Benutzer-EXE bleibt als vorheriger Stand
erhalten; der neue Build ist lokal vorbereitet und öffentlich noch unveröffentlicht.
