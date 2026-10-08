# Bedienbarkeit während Mining-Sync – 8. Oktober 2026

## Ergebnis

Die zuvor reproduzierten Sekundenpausen beim einfachen Tabwechsel sind in zwei
abschließenden Lastläufen nicht mehr aufgetreten. Es wurden keine Funktionen,
Beobachtungen oder historischen Dateien entfernt; BGS-Prognosen bleiben unverändert.
Dies ist ein Quellcode-Fix, noch kein neues installiertes Windows-Release.

## Ursachen und Änderungen

1. **Datei-Metadaten im Qt-Thread:** Journal-Verzeichnisauflösung, Signaturen und
   Status.json wurden regelmäßig während der Bedienung gelesen. Ein gemeinsamer,
   koaleszierter Worker-Snapshot übernimmt jetzt diese Polls. Standortprüfungen
   und EDDN-Profilabgleich lesen dessen Metadaten aus dem Speicher. Profilgeneration,
   Pfadwechsel und ein nach dem Standortlesen geprüfter Journal-Stand verhindern
   die Übernahme verspäteter Ergebnisse. Ein laufender/fehlgeschlagener Poll
   autorisiert keine alten Standort-/Uploaddaten. Fehlversuche werden begrenzt
   wiederholt, nicht über jede Property-Abfrage neu gestartet.
2. **Surface Nav bei jedem Poll:** Status-Lesen und Farm-/Kompass-Projektion lagen
   ebenfalls im Qt-Thread. Die Projektion läuft jetzt im Hintergrund, wird bei
   unveränderten Eingaben wiederverwendet und bei zwischenzeitlichen Standort-,
   Ziel- oder Profiländerungen verworfen/neu berechnet. Live-Balance-Updates nutzen
   denselben gelesenen Status-Snapshot statt eines weiteren Datei-Zugriffs.
3. **Globale Aktualisierung nach Mining-Sync:** Der Stack und die Methodenuhr
   zeigten rund 721 ms in `_finish_mining_market_sync`, insbesondere beim
   `stateChanged.emit()`. Reine Markt-, Ring- und Verifizierungs-Publikationen
   benachrichtigen jetzt die Mining-Domäne. `miningRevision` und die Commodity-
   Auswahl besitzen den passenden Notifier; echte globale Zustandsänderungen
   erreichen den Mining-Bereich weiterhin. Andere Seiten werden nicht wegen
   unveränderter Commander-/Schiffsdaten neu ausgewertet.
4. **Materialseite und konkurrierende Hintergrundarbeit:** Das Inventar wird pro
   Seitenrevision einmal nach QML übernommen statt für mehrere Spalten/Filter
   erneut abgefragt. Große Mining-Merges, History-Schlüsselberechnungen und
   Katalog-Saves geben in Hintergrundthreads regelmäßig kurz Rechenzeit ab.
   Der normale Garbage Collector bleibt eingeschaltet und unverändert.

## Lasttests

Realer Controller und reale asynchrone QML-Seiten, Windows/PySide, 1600 × 1000,
Offscreen-/Software-Renderer. Isolierte Kopie öffentlicher Kataloge mit
349.144 Ringen, 150.000 Marktzeilen und 91.575 Powerplay-Basiseinträgen; synthetisches
Commander-Journal, automatische Journal-Polls aktiv. Netzwerk ausschließlich
öffentliche GET-Abfragen; Uploads blockiert. Die installierte App und originale
AppData-Dateien wurden nicht gestartet, verändert oder gelöscht.

| Messung | Nur Tabs + frischer Sync | Zwei Suchen + Tabs beim frischen Sync |
| --- | ---: | ---: |
| Getestete Tabwechsel | 50 | 50 |
| Langsamster Wechsel | 621 ms (erster Operations-Aufbau) | 492 ms (Materials) |
| Größter Eventloop-Abstand während Tabwechseln | 342 ms | 404 ms |
| Eventloop-Pausen über 500 ms während Bedienung | 0 | 0 |
| QML-Fehler | 0 | 0 |

Im vorherigen Lasttest waren beim Tabwechsel bis zu 2.320 ms und im gesonderten
Diagnoselauf 2.303 ms gemessen worden. Die Live-Serverantworten und Katalogstände
sind nicht byteidentisch; dies ist kein kontrollierter Prozent-Beschleunigungswert.

Tabwerte im vollständigen Suchlauf (je zehn Wechsel):

| Seite | Median | Maximum |
| --- | ---: | ---: |
| Operations | 33 ms | 165 ms |
| Materials | 89 ms | 492 ms |
| Engineering | 36 ms | 68 ms |
| CMDR | 33 ms | 60 ms |
| Mining Finder | 33 ms | 177 ms |

Die gesamte erste 100-Treffer-Suche lieferte lokale Ergebnisse nach 2,427 s und
war nach 48,728 s inklusive Online-Nachprüfung ruhig; die Wiederholung behielt
Ergebnisse nach 0,003 s und wurde nach 23,656 s ruhig. Sämtliche veröffentlichten
Listen enthielten 100 Zeilen, keine wurde zwischenzeitlich geleert. 47/47 bzw.
12/12 Nachprüfungen wurden abgeschlossen; das bedeutet ausdrücklich nicht, dass
100 Routen belegte Powerplay-/Marktdaten besitzen. Fehlende Evidenz bleibt unbekannt.
Kein Endergebnis lag außerhalb des letzten Verifizierungs-Snapshots.

Maximale Eventloop-Abstände der vollständigen Suche: 475 ms erste Suche,
351 ms Wiederholung. Markt-Abschluss-Publikationen lagen bei 93–103 ms statt
der zuvor gemessenen rund 721 ms. Der Prozess erreichte 1.070 MiB Spitzen-RSS;
dieser Fix beansprucht keine zusätzliche große RAM-Einsparung.

## Grenzen und Nachweis

- Der erstmalige App-Start ist von der bereits geöffneten Bedienoberfläche zu
  unterscheiden: bis zur Testbereitschaft etwa sieben Sekunden. Ein längerer
  Eventloop-Abstand während Startup ist in den Rohdaten sichtbar. Ein kalter
  Seitenaufbau ist ebenfalls nicht gleich einem bereits besuchten Tab.
- Offscreen-QML misst Eventloop und Seiten-Erstellung, nicht physisches
  Klick-bis-Bildschirm-Latenzverhalten des installierten D3D-Renderers. Deshalb
  wird keine Garantie für jede Hardware/Lastsituation behauptet.
- Kurze echte Worker-Pausen können einen großen Hintergrund-Merge geringfügig
  verlängern. Ergebnisse, Reihenfolge, Frischeprüfung und Datenumfang ändern
  sich dadurch nicht. Online-Abfragen bleiben naturgemäß netzabhängig.
- Neue Regressionstests prüfen: kein Datei-I/O durch periodische Qt-Polls,
  Profil-/Pfad-/Shutdown-Fences, fehlgeschlagene Polls, keine Freigabe alter
  Standortdaten während eines Polls, koaleszierte und neu basierte Surface-
  Projektionen, Status-Balance ohne erneuten Dateizugriff, bereichsspezifische
  Benachrichtigungen und Worker-Scheduling ohne ausgelassene Datensätze.
- Gesamtsuite: **1.180 Tests erfolgreich** (134,798 s). Danach zusätzlich die
  44 Journal-/Surface-Tests erneut erfolgreich, einschließlich der Absicherung
  gegen wiederverwendete Objekt-IDs in koaleszierten Surface-Snapshots.
  `git diff --check` und Repository-Hygieneprüfung erfolgreich.

Rohmessungen: `.test-tmp/mining-tabs-polls-live-20261008/final-tabs-result.json`
und `result.json`, einschließlich Quellcode-Hashes, Thread-Stacks, GC-Zeiten,
HTTP-Zeiten und Prüffortschritt. Der zusätzliche Poll-Fehler-/Pfadkonsistenzschutz
wurde danach durch Unit-Tests geprüft; ebenso die Referenzhaltung kleiner
Surface-Eingabesnapshots gegen Objekt-ID-Wiederverwendung. Die Performance-Läufe enthalten bereits
alle hier beschriebenen performancewirksamen Änderungen.

Die ausschließlich für diese Messungen erzeugten Profil-/Journal-Kopien wurden
nach Testabschluss entfernt (2,531 GiB). Messprotokolle und Quellcode-Hashes
bleiben erhalten. Die Originaldaten sind unverändert; aus den Originalen können
bei Bedarf erneut isolierte Testkopien erstellt werden.

Keine Commit-, Push-, Release-, Neustart- oder Shutdown-Aktion ausgeführt.
