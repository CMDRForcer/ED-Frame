# Paket 2: Startzeit und RAM — 2026-10-09

## Ergebnis

Der große lokale Ring- und Powerplaybestand wird jetzt erst bei Bedarf geladen:
beim Öffnen des MiningFinders, einer entsprechenden Suche oder bei neuen
öffentlichen Beobachtungen, die mit dem vorhandenen Bestand zusammengeführt
werden müssen. Andere Seiten laden ihn nicht vorsorglich. Wer zuletzt den
MiningFinder geöffnet hatte, bekommt ihn beim nächsten Start weiter vorbereitet.

Vorhandene Dateien, Historien, Offline-Abdeckung, Filter, Berechnungen,
Aktualitätsregeln und BGS bleiben erhalten. Kein Commit, Push, Release,
Serverdeployment oder Austausch der installierten App in diesem Durchgang.

## Funde und Änderungen

- Der Start lud sämtliche Ringe und Powerplaydateien, obwohl nur Operations
  geöffnet war. Die Initialisierung erfolgt nun einmalig und asynchron auf
  tatsächliche Nutzung. Wiederholte Getter/Seitenwechsel starten keinen zweiten
  Loader.
- Bereits beim Einlesen wurde ein globaler Ring-Zuordnungsindex gebaut und
  dauerhaft gehalten. Filter und Systemvorschläge brauchen diesen Index nicht.
  Er entsteht jetzt erst im Worker einer tatsächlichen Zusammenführung.
- Zwei Merge-Pfade kopierten den globalen Index zuerst beim Dispatch und danach
  nochmals im Worker. Der Worker übernimmt jetzt diese bereits private Kopie;
  öffentliche Hilfsaufrufe behalten ihren unveränderten Copy-on-write-Standard.
- Ohne neue Powerplaydaten wurde trotzdem eine zweite Liste angelegt. Unveränderte
  geladene Listen werden jetzt direkt übernommen. Die Lade-Future wird nach
  Veröffentlichung freigegeben, damit sie alte Kataloggenerationen nicht hält.
- Der Oberflächentest entdeckte bei der neuen Ladeanzeige eine rückgekoppelte
  QML-Bindung. Die Benachrichtigung erfolgt jetzt erst im nächsten Qt-Durchlauf;
  ein eigener Regressionstest sichert das ab.

## Schutz vor Datenverlust

„Noch nicht geladen“ ist ausdrücklich kein leerer, speicherbarer Katalog.
Neue Ring- und Powerplaybeobachtungen warten auf den bestehenden Bestand und
werden danach zusammengeführt; auch die Kennzeichnung als Suchaktualisierung
bleibt erhalten. Generation, Profil, Dateipfad und Lade-Token werden vor der
Veröffentlichung geprüft. Doppelte oder verspätete Fertigmeldungen werden verworfen.

Ein Profilwechsel wartet nicht synchron auf das Einlesen. Anstehende Daten des
alten Profils werden vor dem Wechsel verarbeitet. Beim Schließen werden bereits
fertige Worker-Ergebnisse auch ohne zugestellte Qt-Fertigmeldung übernommen;
falls neue Beobachtungen vorliegen, wird vor dem abschließenden Speichern der
alte Bestand geladen. Ohne neue Miningdaten erfolgt beim Schließen kein Laden.
Bei einem tatsächlichen Ladefehler wird die alte Datei nicht überschrieben;
neue Fakten werden beim Schließen, soweit schreibbar, in der Historie gesichert.
Ein Fehler hat eine Wiederholungsfrist statt einer Getter-gesteuerten Ladeschleife.
Ein ausdrücklicher Reset wartet vor dem Archivieren ebenfalls auf den Bestand.

## Kontrollierter Vergleich

Native App aus dem Quellcode, Offscreen-/Software-Rendering, identische öffentliche
JSON-Testkopien (SHA-256 geprüft), synthetisches Journal, Startseite Operations,
kein Netzwerk und ein leerer Test-Marktstore. Keine Messung der installierten EXE,
der Live-Suche oder der GPU-/Eingabelatenz. Einzelmessungen, keine universelle
Geschwindigkeitsgarantie.

| Messpunkt | Vorher | Nachher |
| --- | ---: | ---: |
| Oberfläche initialisiert | 2,96 s | 1,34 s |
| Operations mit Journal bereit | 3,34 s | 1,37 s |
| RAM nach 12 s auf Operations | 688,4 MiB | 176,3 MiB |
| RAM nach Laden des MiningFinders | 695,8 MiB | 613,7 MiB |
| Vorab erzeugte Indexeinträge | 391.212 | 0 |

Nach dem Mining-Laden in beiden Fällen vollständig vorhanden: **391.212 Ringe,
91.575 Powerplay-Katalogeinträge und 49.868 Powerplay-Beobachtungen**. Die beiden
wiederholten Nachherläufe lagen bei 1,35/1,34 s bis zur Oberfläche und rund
178/176 MiB auf Operations. Aktive neue EDDN-Beobachtungen können das Laden
früher auslösen; dann gilt die niedrigere Operations-RAM-Zahl nicht dauerhaft.

**Trade-off:** Der erste Mining-Aufruf ohne vorherigen Bedarf lädt den 342-MB-
Ringbestand plus Powerplaydateien einmal im Hintergrund. Das dauerte hier
**7,54 s**, statt beim vorab geladenen Bestand rund 1,03 s bis zur ersten
Miningansicht. Das ist keine Beschleunigung der ersten Mining-Suche. Die
Oberfläche wird währenddessen nicht synchron angehalten; der größte gemessene
Qt-Timerabstand während dieses Ladens betrug 137 ms, das 95. Perzentil 12 ms.
Danach wird derselbe Bestand weiter genutzt, nicht bei jedem Tabwechsel neu geladen.
Beim Schließen mit ganz neuen, noch nicht zusammengeführten Daten kann die
abschließende Sicherung entsprechend länger dauern.

Um diesen verbleibenden Erstzugriff ohne Verlust der Offline-Abdeckung zu
verkürzen, wäre der nächste Datenarchitektur-Hebel ein regional abfragbarer
Ring-Speicher statt des globalen JSON. Das wurde hier nicht durch eine ungefragte
Migration oder Löschung vorhandener Daten vorweggenommen.

Messartefakte:

- `.test-tmp/startup-catalog-before-20261009-01/result.json`
- `.test-tmp/startup-catalog-after-20261009-04/result.json`
- Wiederholungen/Diagnose ebenfalls unter `.test-tmp/startup-catalog-*`.

Die erste Nachher-Diagnose erbte versehentlich die im Test gespeicherte letzte
Seite MiningFinder. Sie zählt nicht als Vergleich für verzögertes Laden auf
Operations. Der Benchmark setzt inzwischen die Startseite explizit, prüft die
echten Eingabedateien und hasht große Dateien gestreamt, ohne den RAM-Peak durch
eine zusätzliche komplette Byte-Kopie zu verfälschen.

## Prüfung

- **1.231 App-Tests grün**, davon 18 neue Lade-/Persistenz-/RAM-Vertragstests.
- Vollständiger nativer QML-Smoke: alle Seiten, Dialoge, Overlays,
  Seitenzustands-Persistenz und Laufzeitprüfung grün.
- Syntaxprüfung, Repository-Hygiene einschließlich neuer Dateien und
  `git diff --check` bestanden.
- Original-AppData ausschließlich als Quelle öffentlicher JSON-Kopien gelesen;
  keine Originaldatei verändert, gelöscht oder komprimiert. Alle Testschreibvorgänge
  wurden in isolierte Profile unter `.test-tmp` geleitet.

Die großen erzeugten Testprofile wurden nach Abschluss entfernt: **2.258,82 MiB**
freigegeben, ausschließlich reproduzierbare Kopien. Mess-JSONs, Eingabe-Manifeste
und Testlogs bleiben erhalten. Original-AppData wurde nicht bereinigt.
