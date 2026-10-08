# MiningFinder: Ausgangsmessung 1.5.40

Stand: 8. Oktober 2026. Gemessen wurde der freigegebene Anwendungscode von
Commit `ba73e0d65e065faa0620644985a5b2cd08a4941f` (Tag `1.5.40`).
Dies ist Punkt 1 des vereinbarten Fahrplans: messen, noch nicht umbauen.

## Kurzfazit

Erste Treffer erscheinen nach 2,8–3,3 Sekunden. Das ist aber kein fertiges,
nachgeprüftes Ergebnis: Die Liste wird anschließend mehrfach ergänzt.
Eine reproduzierbare QML/Python-Typinkompatibilität verhindert außerdem den
Aufruf der gezielten Nachprüfung. Diesen Fehler zuerst beheben; danach
Speicher, wiederholte Abfragen und die gestufte Ergebnisveröffentlichung angehen.

## Messbedingungen und Grenzen

- Echte Controller, Hintergrundarbeiter und asynchrone QML-Seiten; Python
  3.13.15, PySide6/Qt 6.11.2. Separater Prozess, offscreen/Software-Renderer.
  Keine Messung der installierten EXE, von D3D oder Maus-bis-Bild-Latenz.
- Zwei frische Prozesse auf demselben öffentlichen Katalog-Grundstand:
  323.797 Ring-Kandidaten, 150.000 aktuelle Marktzeilen und 91.575
  Powerplay-Katalogzeilen plus gespeicherte öffentliche Beobachtungen.
- Shanteneri, Platinum, Laser, Powerplay Merits / Aisling Duval / Reinforce,
  250 LY, Large Pad, mindestens 5.000 t, maximal 500.000 t, Marktalter 1 h;
  zuerst 30, dann 100 Ergebnisse. Je eine Folgesuche im selben Prozess.
- „Erstsuche“ bedeutet frischer App-Prozess, nicht geleerte Windows-/Server-Caches.
  Start und Katalogaufbau sind getrennt von der Suchzeit ausgewiesen.
- Öffentliche Kataloge wurden kopiert; SQLite über eine `mode=ro`-Verbindung
  und konsistentes Backup gelesen. Keine echten Zugangsdaten, Upload-Warteschlangen
  oder Commander-Journalhistorien wurden in die Testprofile übernommen.
- Nur öffentliche GET-Abfragen waren erlaubt. EDDN-Listener, Sharing-Pfade und
  ausgewählte periodische Netzwerkjobs waren deaktiviert. Der normale
  State-Finds-Startsync lief mit und wurde separat im HTTP-Trace erfasst.
  BGS-Prognoselogik wurde nicht verändert.
- Die tatsächliche Windows-App lief gleichzeitig weiter: Fenstertitel
  **1.5.39 – ED-Frame**, rund **2.030 MiB RSS**, Prozessspitze **2.081 MiB**.
  Diese Werte sind keine 1.5.40-Messwerte. Rechner: ca. 31,8 GiB nutzbarer RAM;
  während einer Stichprobe ca. 16,4 GiB frei. Systemlast und Live-Serverdaten
  waren nicht eingefroren; Einzelmessungen sind keine Geschwindigkeitsgarantie.
- Ein erster Pilotlauf ohne feste Journalposition wurde für den
  Erst-/Folgesuchvergleich verworfen: Eine QML-Bindung setzte das Testsystem
  auf „Unknown system“. Die folgenden Tabellen enthalten nur die korrigierten Läufe.

## Suche und Speicher

Alle Suchzeiten beginnen beim Auslösen der Suche. Die letzte Listenänderung
ist **nicht** gleichbedeutend mit abgeschlossener Verifizierung.

| Messung | 30 Treffer | 100 Treffer |
| --- | ---: | ---: |
| App, Journal und lokaler Katalog bereit | 5,84 s | 5,88 s |
| RSS bei Bereitschaft | 922,7 MiB | 925,5 MiB |
| Erstsuche: erste Liste | 2,827 s | 3,265 s |
| Erstsuche: letzte Listenänderung | 46,327 s | 45,586 s |
| Erstsuche: Listenveröffentlichungen | 4 | 3 |
| Folgesuche: vorhandene Liste wiederverwendet | 0,002 s | 0,002 s |
| Folgesuche: letzte Listenänderung | 37,023 s | 50,397 s |
| Folgesuche: weitere Veröffentlichungen | 3 | 3 |
| Prozess-RSS-Spitze über beide Suchen | 1.240,0 MiB | 1.248,1 MiB |
| Tatsächlich gestartete gezielte Nachprüfung | nein | nein |

Der Messautomat wartet nach der letzten Änderung zusätzlich 1,5 Sekunden ohne
Plan-/Sync-Aktivität. Diese Sicherheitszeit ist in den obigen Änderungszeiten
nicht enthalten. Die 2 ms der Folgesuche bedeuten nur Wiederverwendung der
vorherigen Anzeige, keinen neuen Servernachweis.

Im korrigierten 30-/100-Treffer-Vergleich wurde die Liste während der Folgesuche
nicht geleert. Spätere Änderungen blieben jedoch bestehen. Dass die
100er-Folgesuche hier länger dauerte, beweist keine entsprechend höhere Kosten
der Ergebnisanzahl: Beide Läufe stellten gleich viele Mining-HTTP-Abfragen.

## Reaktionsfähigkeit

Ein präziser Qt-Timer tickte mit 10 ms Sollintervall. Die Werte messen Abstände
zwischen Ereignisschleifen-Aufrufen, keine Render-Frametimes.

| Phase | p95 Timerabstand | Größter Abstand | Abstände über 500 ms |
| --- | ---: | ---: | ---: |
| 30: Erstsuche | 13,3 ms | 684 ms | 2 |
| 30: Folgesuche | 11,4 ms | 767 ms | 2 |
| 100: Erstsuche | 12,4 ms | 619 ms | 4 |
| 100: Folgesuche | 11,1 ms | 1.173 ms | 5 |

Meist bleibt die Ereignisschleife schnell, einzelne spürbare Stocker sind aber
noch vorhanden. Der erste Timerabstand beim Start lag bei ca. 1,22 s; er umfasst
auch die Zeit vor Eintritt in die normale App-Ereignisschleife.

Tabwechsel während eines zusätzlich gestarteten Netz-Syncs:

| Zielseite | Loader sichtbar/bereit nach |
| --- | ---: |
| Operations | 30 ms |
| Materials | 126 ms |
| Engineering | 45 ms |
| CMDR | 60 ms |
| MiningFinder | 32 ms |

Die Bereitschaft wurde alle 25 ms geprüft. Alle fünf Wechsel erfolgten bei
aktivem Sync, aber nur in dessen früher Netzphase. Dies ist kein Nachweis für
ruckelfreie Bedienung über jede Merge-/Speicherphase. Vorhandene persönliche
Journalhistorien und reale Fleet-Daten fehlen im Testprofil.

## Konkrete Funde

### 1. Nachprüfungsaufruf scheitert vor Eintritt in Python

In beiden Prozessen, bei Erst- und Folgesuche, meldet
`qml/pages/MiningFinderPage.qml:565`:

> TypeError: Passing incompatible arguments to C++ functions from JavaScript is not allowed.

Der Produktionsslot ist als
`verifyMiningRoutes(PyObject,QString,QString,int,int,QString)` registriert.
QML übergibt nach dem Kopieren der Routen ein natives JavaScript-Array.
Ein isolierter Vertragstest mit denselben sechs Argumenttypen bestätigt:

| Slotvertrag für die Routen | Python-Aufrufe | Ergebnis |
| --- | ---: | --- |
| `object` / `PyObject` wie Produktion | 0 | derselbe Typfehler |
| `QVariantList` im Diagnose-Gegenversuch | 1 | kein Typfehler |

Der Suchrevisionsmarker wird bereits vor dem gescheiterten Aufruf gesetzt.
Die Anzeige kann deshalb weiter „Ready · verifies top routes after search“
zeigen, obwohl keine gezielte Prüfung gestartet ist. In den Messungen gab es
keinen `miningVerificationChanged`-Aufruf und keine ausgeführten Prüfungen.
Bereits aus regionalen/lokalen Fakten abgeleitete `VERIFIED`-Zeilen sind davon
zu unterscheiden. Eine vollständige Endzeit inklusive gezielter Nachprüfung
kann mit unverändertem 1.5.40 daher nicht seriös angegeben werden.

### 2. Auch die Folgesuche überträgt den regionalen Bestand erneut

Je Suche: **26 Ringseiten + 59 Powerplay-Seiten + 2 Marktabfragen = 87 GETs**.
Die Mining-Antwortkörper umfassen insgesamt ca. **27,5 MiB pro Suche**;
das sind bereits dekomprimierte Antwortgrößen, keine exakten Netzwerk-Bytes.
Rund 24.450 Ring-Kandidaten und 33.100 Powerplay-Zeilen werden verarbeitet,
obwohl nur 30 bzw. 100 fertige Routen angezeigt werden.

| Abrufdauer je Domäne | 30 Erst | 30 Folge | 100 Erst | 100 Folge |
| --- | ---: | ---: | ---: | ---: |
| Ringe inkl. Projektion/Zusammenführung | 33,735 s | 25,164 s | 33,580 s | 36,981 s |
| Powerplay | 8,333 s | 5,516 s | 8,802 s | 5,849 s |
| Märkte | 1,261 s | 0,939 s | 1,384 s | 0,890 s |

Die Domänen laufen parallel; die Zeiten dürfen nicht addiert werden.
Die Ringdomäne ist hier die längste. Im Trace fehlen sowohl `known_revision`
als auch `snapshot_revision`; ein wiederverwendbarer versionierter Ring-Snapshot
wurde nicht genutzt. Den Server-/Clientvertrag prüfen, bevor man einen
Geschwindigkeitsgewinn durch den vorhandenen Snapshot-Code verspricht.

Zusätzlich liefen beim Start 29 State-Finds-Seiten, davon 28 während der ersten
Suche. Damit stieg diese Phase auf 115 HTTP-Abfragen und ca. 47,7 MiB
Antwortkörper. Dies ist Hintergrundkonkurrenz, keine zusätzliche Mining-Funktion
und kein Anlass, BGS-Prognosen zu verändern.

### 3. Wiederholte Planung und Powerplay-Indexierung

Der instrumentierte 100er-Lauf führte während der Erstsuche **5** Planungen
(kumuliert **9,824 s**) und während der Folgesuche **4** Planungen
(kumuliert **8,997 s**) aus. Eine einzelne Planung dauerte bis **3,077 s**.
Es handelt sich um Laufzeit der Hintergrundfunktionen, nicht reine CPU-Zeit.

Der Powerplay-Index wurde ebenfalls 5 + 4 Mal neu aufgebaut. Darauf entfielen
**3,649 s + 3,287 s**, je Aufruf bis **1,144 s**. Der Index sortiert Fakten
nach Beobachtungszeit und baut System-/Power-Zuordnungen neu auf.
Ein revisionsgebundener Index und zusammengefasste Planungsanlässe sind hier
konkrete Ansatzpunkte; Aktualität und neuere Fakten müssen erhalten bleiben.

### 4. Speicherbedarf ist weiterhin relevant

Schon vor der Suche benötigt der große öffentliche Katalog im vollständigen
Qt/QML-Testprozess rund 0,9 GiB RSS. Während Abruf, Merge und Planung steigt
das auf rund 1,2 GiB. Weniger sichtbare Ergebniszeilen ändern das kaum.
Ein bedarfsgeladener Ringindex bleibt daher sinnvoll, beseitigt aber weder
den Slotfehler noch die wiederholten Netztransfers automatisch.

Die ca. 2,0 GiB der laufenden 1.5.39-Instanz sind wegen anderer Laufzeit,
Seiten, Historien und Integrationen nicht direkt damit vergleichbar.
Aus dieser Stichprobe folgt noch kein nachgewiesenes Speicherleck.

## Reihenfolge nach dieser Messung

1. QML/Python-Vertrag der Nachprüfung korrigieren und mit echtem QML-Aufruf
   regressionsprüfen. Danach vollständige Prüfzeiten neu messen.
2. Ring- und Powerplay-Zugriff bedarfsgeladen/revisionsgebunden machen;
   vorhandene Daten und Offline-Abdeckung erhalten. Snapshot-Wiederverwendung
   auf dem tatsächlichen Server nachweisen, nicht nur im synthetischen Test.
3. Abruf, gezielte Batch-Prüfung und finale Planung koordinieren; Änderungen
   sammeln und neue Suchergebnisse einmal vollständig veröffentlichen.
4. Fortschritt/Abbrechen und ehrliche Fehler-/Timeoutzustände beibehalten.
   Erste fertige Ergebnisse können später erscheinen; unbekannt bleibt unbekannt.

## Artefakte und Umfang

Wiederholbares Messwerkzeug: `tools/benchmark_mining_baseline.py`.
Rohmessungen verbleiben lokal unter `.test-tmp/baseline-1.5.40-30-v2/result.json`
und `.test-tmp/baseline-1.5.40-100-final/result.json` (Git-ignoriert).
Die großen, eigens erzeugten Testprofilkopien wurden nach der Auswertung entfernt
(6,50 GiB); sie lassen sich aus den Originalkatalogen erneut erzeugen.
Messwerte und Inventare bleiben erhalten. Bestehende ED-Frame-Nutzerdaten werden
weder gelöscht noch komprimiert oder migriert. Die laufende App darf ihre eigenen
Daten weiterhin aktualisieren.

Kein Anwendungscode geändert, kein Serverdeploy, kein Commit/Release und kein
Herunterfahren des Rechners. Der Slot-Gegenversuch ist Diagnose, noch kein Fix.
