# Mining Finder: regionales Laden und Zusammenführen — 08.10.2026

## Ergebnis und Auslieferungsstand

Die App bereitet Ringdaten jetzt parallel zu noch laufenden Powerplay-/Marktabfragen
auf. Markt- und Powerplay-Zustand werden vor der ersten Ring-Veröffentlichung
übernommen. Eine vorbereitete Zusammenführung wird nur für den exakt zugehörigen
Katalog, Profilpfad, Profilgeneration, Reset und Katalogrevision veröffentlicht.
Bei konkurrierenden Änderungen bleibt der bisherige Rebase-/Retry-Weg erhalten.

App-Code für **Version 1.5.42** implementiert. Die Messungen unten erfolgten vor
der Veröffentlichung mit dem Quellcode. Ein Update der installierten App ist
nicht Teil der Performance-Messungen.
Die beschriebenen Regionsänderungen wurden nach ausdrücklicher Freigabe am
**09.10.2026 auf dem Server deployt**. Nur die API wurde neu gestartet;
Datenbank, Collector und Caddy liefen weiter. Das separate Snapshot-Revisionsprotokoll
ist bewusst nicht Teil dieses Deployments.

## Gefundene Bremsen und Änderungen

- Bisher: erst sämtliche Regionen laden, danach die Ringe zusammenführen.
  Jetzt: vollständige Ring-Domäne sofort im Hintergrund zusammenführen; andere
  Netzwerkabfragen laufen weiter. Keine Teilseiten-Veröffentlichung.
- Pro Ring wurde erneut ein Katalog gruppiert und sortiert. Die gemeinsame
  Einzelring-Kombination vermeidet diese Arbeit, ohne Messproben, Herkunft,
  Community-Korrekturen, Freshness oder lokale Erträge zu verändern.
- Gleiche Standard-Herkunftsbelege werden ohne wiederholte JSON-Kodierung erkannt.
  Ungewöhnliche/nestende Belege behalten den bisherigen kanonischen JSON-Weg.
- Der Download bleibt auf dem heutigen Server teuer: 26 Ring- und 59 Powerplay-Seiten.
  Ein rein lesender SQL-Plan zeigte 127.015 verworfene fremde Datensätze für die
  erste Seite. Das Erzwingen einer vollständig vorgefilterten Region war langsamer
  (5,54 statt 3,57 Sekunden) und wurde verworfen.
- Vorbereitet: opt-in 5.000 statt 1.000 Ringe und 1.000 statt 200 Powerplay-Systeme
  pro Seite. Alte Server ignorieren den Parameter und funktionieren unverändert.
  Die bisherigen Gesamtbudgets von 50.000 Ringen/20.000 Powerplay-Systemen sowie
  die Kennzeichnung begrenzter/unvollständiger Daten bleiben erhalten.
- Vorbereitet: GiST-XY-Index mit konservativer Box plus Z-Grenzen. Die bisherige
  exakte Kugelabfrage bleibt zusätzlich bestehen. Keine Erweiterung nötig.
  Community-Referenzen behalten trotz größerer Seiten die alte Erstseiten-Semantik.

## Messungen

Isolierte öffentliche Katalogkopien, ausschließlich GET-Anfragen, synthetisches
Journal, 100 angeforderte Ergebnisse, Shanteneri/Platinum/250 LY. Native QML-App
offscreen mit Software-Renderer; keine Messung physischer D3D-Eingabe-/Paint-Latenz.
Live-Serverdaten und Ausgangskatalogumfang änderten sich zwischen den Läufen etwas;
die Live-Zeiten sind einzelne Messungen, keine statistische Garantie.

| Messung | Vorher | App-Optimierung | Finaler Abschlusslauf |
| --- | ---: | ---: | ---: |
| Erstsuche vollständig ruhig, inklusive Verifizierung | 53,421 s | 52,601 s | 44,864 s |
| Erneute Suche vollständig ruhig | 23,216 s | 18,403 s | 18,089 s |
| Geladene regionale Ring-Identitäten | 24.456 | 24.456 | 24.456 |
| Angezeigte Ergebnisse | 100 | 100 | 100 |
| Endgültige Routen außerhalb des Verifizierungssnapshots | 0 | 0 | 0 |
| QML-Fehler | 0 | 0 | 0 |

Die erneute Suche gewinnt in diesen Läufen etwa 21–22 %. Die Erstsuche bleibt
durch die unveränderte Serverabfrage dominiert: Der reine Ringdownload schwankte
zwischen 27,037 und 34,787 Sekunden. Die Verbesserung des finalen Kaltlaufs darf
deshalb nicht allein dem App-Code zugeschrieben werden. Größere Seiten und der
räumliche Index sind in diesen Zahlen **noch nicht aktiv**.

Finaler Tabtest: 50 Wechsel, davon 42 während laufender Arbeit, Median 34,14 ms,
Maximum 398,66 ms. Ein Eventloop-Abstand von 519 ms bei der ersten Veröffentlichung;
keine mehrsekündigen Hänger im Such-/Tabtest. Startup bleibt separat: dort wurden
ebenfalls längere Abstände gemessen. Dies ist keine Garantie für jeden Rechner.
RAM-Spitze einschließlich Tabtest 1.119,4 statt 1.105,0 MiB bei leicht größerem
Ausgangskatalog; keine Behauptung einer RAM-Reduktion durch diese Änderung.

Kontrollierter Replay mit 359.092 bestehenden und 24.456 eingehenden Ringzeilen:
identischer Ergebnis-Hash `fbb255328c7578d63d072806215818f2c476ad17a30aca1af49ad21bb0241656`,
je 24.456 archivierte Eingangsfakten und verdrängte Katalogzeilen. Profilierter
Gesamtlauf 8,074 → 7,670 s; Profilerzeiten sind keine UI-Laufzeiten.

Rein lesender Serververgleich in derselben Repeatable-Read-Transaktion:
1.001 alte Zeilen identisch zum Präfix der 5.001 größeren Zeilen; mit zusätzlicher
Box waren alle 5.001 Rohdatenzeilen einschließlich Reihenfolge identisch.
Der neue Index wurde dabei noch nicht angelegt; seine Beschleunigung ist ungemessen.

## Absicherung

- Vollsuite: 1.198 App-Tests grün, danach 337 Mining-Tests auf dem aktualisierten
  Veröffentlichungspfad einschließlich zwei zusätzlicher Abschlussprüfungen grün.
- 105 Server-Tests grün; Repository-Hygiene und `git diff --check` grün.
- Zusätzlich 83 betroffene Responsiveness-/Katalog-/Historientests auf dem
  abschließenden Codezustand grün.
- Explizite Tests für Cache-Hits, Legacy-/Großseiten, Gesamtbudgets, fehlerhafte
  Fortsetzungsseiten, unveränderte Eingaben, Community-/lokale Aggregation,
  Profil/Reset/Pfad/Revision, aktive Konkurrenz-Merges, Shutdown, Archiv-Fallback
  und konsistente Markt-/Powerplay-Daten bei Ring-Benachrichtigungen.
- Vorhandene AppData-Dateien, historische Beobachtungen und BGS-Prognosen unverändert.

Messartefakte: `.test-tmp/mining-regional-before-20261008/result.json`,
`.test-tmp/mining-regional-after-20261008/result.json` und
`result-pre-publication-order.json`. Ausschließlich die selbst angelegten großen
Profil-/Journal-/Replay-Kopien wurden entfernt (4,455 GiB); Messberichte bleiben
erhalten. Die Originaldateien wurden weder gelöscht noch verändert. Die Testkopien
können aus den erhaltenen Originalen neu erstellt werden.

## Server-Deployment und Gleichheitsprüfung — 09.10.2026

Die laufende API wurde selektiv erweitert, nicht durch den vollständigen lokalen
Serverstand ersetzt. Ausgangsquellen und laufendes Docker-Image sind gesichert in
`/opt/edframe-deploy-backups/regional-20261009-01`. Quellhash-Prüfungen verhindern
das Überschreiben abweichender Zwischenstände; bei einem Fehler stellt das
Deployment-Skript die vorherige API wieder her. HTTPS `/healthz`: 200 / `ok`,
API-Version 0.8.1. Keine Katalogdaten gelöscht oder exportiert.

Index nebenläufig mit `CREATE INDEX CONCURRENTLY` angelegt, ohne Neustart der
Datenbank: gültig/bereit, 68.485.120 Bytes (65,31 MiB), Aufbau 3,094 Sekunden.
Die persistierte Schemaänderung betrifft ausschließlich diesen zusätzlichen Index.
Im SQL-Vergleich: 5.001 identische Zeilen, 5,634 s ohne Box gegenüber 3,136 s
mit indexierter Box. Die exakte Kugelprüfung bleibt bestehen.

Vollständiger Legacy-/Großseitenvergleich in **derselben rein lesenden
Repeatable-Read-Transaktion** mit unverändertem Zeitfilter:

| Domäne | Kleine Seiten | Große Seiten | Gleichheitsnachweis |
| --- | ---: | ---: | --- |
| Ringe | 26 Seiten / 50,332 s | 6 Seiten / 14,584 s | Alle 25.351 Zeilen samt Reihenfolge identisch |
| Community-Referenzen | 22 | 22 | Gesamter Inhalt identisch |
| Powerplay | 57 Seiten / 1,359 s | 12 Seiten / 1,102 s | Alle 31.889 Fakten aus 11.396 Systemen identisch |

Dies sind direkte Serverläufe ohne HTTPS/Client-Zusammenführung, keine App-Zeiten.
Kleine Seiten wurden zuerst gemessen; Cachewärmung beeinflusst Einzelmessungen.
Ergebnisgleichheit ist exakt geprüft, die Zeitwerte sind keine Garantie.
Die bisherigen Seitenlimits für alte Apps und konkrete Systemabfragen bleiben
unverändert; neue Apps nutzen die begrenzten Großseiten ausdrücklich per Parameter.

API-Quellhash: `456a691bbfef64654989cb363ab02921fe143dcd697f5f2ac6ac2b76db7b4ee0`.
Prüfwerkzeug: `server/catalog_service/ops/verify-mining-region.py`.
Deployment-/SQL-Nachweis: `.test-tmp/regional-deploy-20261009-01/verification-results.json`.
Erneut 337 Mining-Tests und 105 Server-Tests grün, zusätzlich fünf Regionsprüfungen
direkt gegen die selektiv bereitgestellte API. Hygiene / `git diff --check` grün.

## Native App mit deploytem Server — 09.10.2026

Gleicher Suchaufbau wie oben: 100 Ergebnisse, Shanteneri/Platinum/250 LY,
Powerplay Merits, isolierte öffentliche Katalogkopie, GET-only, natives QML
offscreen mit Software-Renderer. Der Ausgangskatalog ist inzwischen größer:
391.212 statt 359.960 Ringkandidaten. Markt-/Powerplay-Daten und Zeitfilter sind
live; dies ist kein kontrollierter Vergleich identischer Frontend-Eingaben.

| Messung | Vorheriger App-Code-Lauf, Legacy-Server | Nach Deployment |
| --- | ---: | ---: |
| Erste lokale Ergebnisse | 2,587 s | 2,624 s |
| Erstsuche vollständig beruhigt, einschließlich Verifizierung | 44,864 s | 40,477 s |
| Erneute Suche vollständig beruhigt | 18,089 s | 18,781 s |
| Reiner kalter Ringdownload | 27,037 s | 21,739 s |
| Kalter Powerplay-Download | 6,492 s | 4,034 s |
| Vollständige Ringvorbereitung im Hintergrund | 4,919 s | 5,353 s |
| Angezeigte Ergebnisse | 100 | 100 |
| Endgültige Routen außerhalb des Verifizierungssnapshots | 0 | 0 |
| QML-Fehler | 0 | 0 |

Beide regionalen Domänen vollständig und nicht budgetbegrenzt: 24.457 nach
Client-Normalisierung zusammengeführte Ringidentitäten in sechs Seiten und
31.889 Powerplay-Fakten in zwölf Seiten. Im erneuten Lauf wurden die Ringdaten
aus dem bestehenden Regionscache wiederverwendet; Powerplay blieb frisch geladen.
53 konkret nachgeprüfte Systeme hatten keine aktuelle Powerplay-Evidenz. Das ist
ehrlich fehlende Evidenz, kein Grund zur erfundenen Merit-Verifizierung.

Die Erstsuche ist in diesem Lauf schneller, die erneute Suche **nicht**:
Ringvorbereitung, lokale Verarbeitung und gezielte Markt-/Powerplay-Verifizierung
bleiben relevante Kosten. Größere Seiten allein lösen sie nicht. Frische und
Verifizierung wurden nicht reduziert, um eine bessere Zeit zu behaupten.

45 Tabwechsel, davon 37 bei laufender Synchronisierung: Median 35,853 ms,
Maximum 376,065 ms. Eventloop-Maximum Erstsuche 496,539 ms, erneute Suche
424,661 ms, Tab-/Sync-Test 415,262 ms; keine Pausen über 500 ms in diesen Phasen.
Startup separat: 1.995,032 ms maximale Pause. RAM-Spitze 1.162,0 MiB gegenüber
1.119,4 MiB bei größerem Ausgangskatalog; keine RAM-Reduktionsbehauptung.

Messnachweis: `.test-tmp/mining-regional-deployed-20261009-02/result.json`,
öffentliche Ausgangsdateigrößen in `source-inventory.json`. Der erste Versuch
der isolierten Kopie scheiterte am eingeschränkten SQLite-WAL-Zugriff; nach
freigegebenem lesendem Zugriff wurde eine neue, konsistente Kopie erstellt.
Nur selbst angelegte große Profil-/Journal-Testkopien wurden nach Abschluss
entfernt (3,316 GiB); Ergebnisdateien und Original-AppData bleiben erhalten.
Abschlussprüfung: API gesund, unveränderte Collector-/DB-/Caddy-Container,
Quellhashes stimmen im laufenden Container, rund 12 GiB Serverplatz frei.

## App-Auslieferung — 1.5.42

Die Client-Änderungen sind Bestandteil von Version 1.5.42. Nach gesonderter
Freigabe werden Commit, Push und der geprüfte Windows-Release über den regulären
GitHub-Workflow ausgeführt. Endnutzer müssen diese App-Version installieren;
ein bloßer Neustart installiert keinen neuen App-Code.

Lokale Abschlussprüfungen für den Release: 1.200 App-Tests grün (135,587 s),
105 Server-Tests grün, Syntaxprüfung von 202 Python-Dateien grün,
QML-Oberflächentest für alle geprüften Seiten/Dialoge/Overlays PASS,
Repository-Hygiene einschließlich aller neu vorgemerkten Dateien und Diff-Prüfung grün.
