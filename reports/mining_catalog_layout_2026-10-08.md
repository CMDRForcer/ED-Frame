# Katalog-RAM und kompakte Mining-Merges

8. Oktober 2026. Nächster lokaler Performance-Hebel nach der gebündelten
Planung. Nur Code, Tests und isolierte Messungen; kein Commit, Release,
Serverdeployment oder Neustart der installierten App.

## Ursache und Fix

Bei einem eingefrorenen öffentlichen Katalog mit 342.476 Ringzeilen belegten
allein die äußeren Zeilen-Wörterbücher 271,740 MiB, ohne die eigentlichen
Feldwerte. Sehr viele Zeilen besitzen dieselben Feldnamen, hielten aber
getrennte große Schlüssel-/Hash-Tabellen.

Der JSON-Lader erstellt nun weiterhin normale Python-`dict`-Objekte, nutzt
aber CPythons gemeinsame Feldnamen-Layouts von Instanz-Wörterbüchern. Es gibt
keine eigenen Mapping-Proxys und keine gemeinsam veränderbaren Zeilenwerte.
Die Factory behält höchstens 64 Layouts pro Ladevorgang bzw. Merge-Worker.
Leere, übergroße oder weitere ungewöhnliche Layouts erhalten normale Dicts;
kein Datensatz und kein Feld wird deshalb verworfen.

Neue/geänderte Zeilen werden nach dem Mining-Merge ebenfalls kompakt
angelegt. Unveränderte Zeilen bleiben dieselben Objekte. Der bereits bestehende
Abwurf berechneter Ansichtsfelder bleibt unverändert; originale eingehende und
verdrängte Beobachtungen werden weiter vor der Veröffentlichung archiviert.
Bei Archivfehlern gilt weiterhin die verlustfreie Rückfallstrategie.

Keine Änderung an JSON-Dateiformat, Historie, Datenumfang, Offline-Funktionen,
Filtern, Ranking, Aktualitätsgrenzen, Prüfbudgets oder Netzwerkabfragen.
BGS-Prognosen bleiben unangetastet. Bestehende AppData-Dateien werden nicht
migriert, komprimiert, gekürzt oder gelöscht.

## Kontrollierter Vorher-/Nachher-Vergleich

Gleiche eingefrorene Datei, getrennte Python-3.13.15-Prozesse. Der Plain-Lauf
deaktiviert nur das neue Layout-Sharing; String-Sharing und Domainlogik sind
identisch. Merge von 24.455 verteilt ausgewählten Zeilen, mit echtem SQLite-
Historienarchiv und identischer fester Bewertungszeit. Kein HTTP oder QML.

| Messgröße | Plain | Kompakt |
| --- | ---: | ---: |
| Ringzeilen vor / nach Merge | 342.476 / 342.476 | 342.476 / 342.476 |
| Laden | 3,8794 s | 4,3169 s |
| Äußere Zeilen-Dicts nach Laden | 271,740 MiB | 88,173 MiB |
| Prozess-RSS nach Laden | 661,2 MiB | 451,4 MiB |
| Merge + Historienarchiv | 3,5319 s | 3,5528 s |
| Prozess-RSS nach Merge | 794,6 MiB | 568,2 MiB |
| Prozess-RSS-Spitze bis Mergeende | 834,6 MiB | 620,0 MiB |

Damit rund **210 MiB weniger RSS nach Laden**, **226 MiB nach Merge** und
**215 MiB weniger Spitze** in diesem kontrollierten Ablauf. Die Digest-Werte
der geladenen und der gemergten Gesamtdaten stimmen exakt überein; auch die
eingehenden Originalzeilen bleiben unverändert. Beide Archivläufe fehlerfrei.

### Nachteile und Grenzen

- Das einmalige Laden dauerte in diesem Vergleich rund **0,44 s länger**.
  Layout-Erkennung und die speichersparende Anlage kosten etwas CPU. Der
  Merge war praktisch gleich schnell, nicht nachweislich beschleunigt.
- Die Ersparnis hängt von wiederkehrenden Feldlayouts und vom Interpreter
  ab. Gemessen wurde der tatsächlich verwendete CPython; es gibt keine feste
  garantierte MiB-Ersparnis für jeden Katalog.
- Es werden keine Werte ausgelagert. Daher keine zusätzlichen lokalen
  Lesezugriffe oder neue Netzwerkabhängigkeit, aber der vollständige Katalog
  bleibt weiterhin im RAM. Das ist noch keine speicherarme Regionaldatenbank.
- Große Ringdownloads, Indexaufbauten, Freigaben und andere Merge-/UI-Arbeit
  können weiterhin verzögern. Diese Änderung beweist keine ruckelfreie App.

## Verifikation

- Gesamte Testsuite: **1.162 Tests erfolgreich**, 135,935 s.
- Fünf neue Regressionstests: gewöhnlicher Dict-Typ, Reihenfolge,
  Sonder-/Unicode-/doppelte JSON-Schlüssel, unabhängige Werte, vollständige
  übergroße Datensätze, Factory-Begrenzung, Speicherreduktion unter CPython
  sowie unveränderte Eingaben und Historieninhalte beim Merge.
- Gezielt 177 Katalog-, Batch-, Responsiveness-, Projektions- und Planner-
  Tests erfolgreich. Repository-Hygiene und `git diff --check` erfolgreich.
- Reproduktion: `tools/benchmark_catalog_layout.py` jeweils mit `--mode plain`
  und `--mode shared`, derselben `--catalog`-Kopie und frischen `--output`-
  Dateien. Die Originaldatei wird ausschließlich gelesen.
- Kontrollierte Rohdaten: `.test-tmp/catalog-layout-20261008/plain.json` und
  `shared.json`, einschließlich Quelldigest, Ergebnisdigests und Speicherwerten.

## Isolierter 100-Routen-Suchtest

Echte Controller, Worker und QML-Seiten; offscreen/Software, 1600 × 1000,
synthetischer Commander, nur öffentliche GETs und gesperrte Uploads.
Vorbereitete separate Profilkopie mit 342.646 Ringen, 150.000 Märkten und
91.575 Powerplay-Katalogzeilen plus öffentlichen Beobachtungen. Gleiche
Suchparameter wie im vorherigen Coalescing-Bericht: Shanteneri, Platinum,
Laser, Powerplay Merits/Aisling Duval/Reinforce, 250 LY, 100 Treffer,
Large Pad, Nachfrage 5.000–500.000 t und Marktalter 1 h.

| Messgröße | Vorheriger Coalescing-Lauf | Jetzt mit kompakten Katalogen |
| --- | ---: | ---: |
| RSS bei Startbereitschaft | 950,4 MiB | 732,0 MiB |
| RSS nach beiden Suchen | 1.270,7 MiB | 1.072,1 MiB |
| RSS-Spitze einschließlich Tabtest | 1.400,8 MiB | 1.194,9 MiB |
| Startbereitschaft | 5,901 s | 6,783 s |
| Erste lokale Liste | 2,107 s | 2,285 s |
| Letzte Listenänderung Erstsuche | 65,384 s | 60,473 s |
| Letzte Listenänderung Folgesuche | 19,522 s | 24,046 s |

Das bestätigt die RAM-Reduktion auch in der vollständigen Anwendung, nicht
eine allgemeine Beschleunigung: Live-Daten und Serverlast unterscheiden sich.
Der Ringabruf dauerte diesmal 41,149 s; Powerplay in der Folgesuche 7,741 s
statt zuvor 5,218 s. Für eine reine Layout-Messung ist der eingefrorene
Vorher-/Nachher-Vergleich oben aussagekräftiger.

Erstprüfung: 39 Powerplay- plus sechs Marktziele, 45/45 Checks abgeschlossen;
Folgeprüfung: sechs neue plus sechs gecachte Marktchecks, 12/12 abgeschlossen.
Das heißt nicht 100 vollständig verifizierte Routen. Unbekannte Powerplay-
Fakten und alte Marktwerte bleiben entsprechend gekennzeichnet. Alle sieben
Listenveröffentlichungen hatten 100 Zeilen, ohne Leerung und mit stabiler
Mining-Reihenfolge. Preise/Prüfstatus werden weiterhin nachgeladen.

40 Tabwechsel über Sync, Merge und anschließende Ruhephase: MiningFinder
Median 31 / Maximum 39 ms, Engineering 40 / 94 ms, CMDR 32 / 62 ms,
Materials 131 / 983 ms und Operations 30 / 757 ms. Gemessen bis zur
sichtbaren Seiteninstanz, nicht bis zum fertigen Bild; keine echte Flotte.
Der 10-ms-Qt-Timer hatte p95 11,2 ms in der Erstsuche und 11,5 ms in der
Folgesuche. Die größte Pause während des Tabtests betrug jedoch 1.647 ms.
**Die verbleibenden UI-Spitzen sind nicht behoben.** Weniger RAM allein
beseitigt nicht jede synchrone Freigabe, Veröffentlichung oder GIL-Pause.

Kein QML-/Netzfehler; sämtliche aufgezeichneten Produktions-Quellhashes
stimmen mit dem getesteten Stand überein. Rohdaten und Kopierinventar:
`.test-tmp/mining-compact-catalog-100-20261008-b/result.json` und
`source-inventory.json`. Nicht die installierte EXE, keine Messung realer
Maus-bis-Bild-Latenz. State-Finds-Startsync lief mit.

Nach Ende sämtlicher Messprozesse wurden nur die selbst erzeugten öffentlichen
Katalog-/Journal-Kopien und die beiden Benchmark-Historienarchive entfernt,
zusammen 2,868 GiB. Auch die unvollständige erste Testkopie wurde bereinigt.
Rohmessungen und Kopierinventar bleiben erhalten; die Originaldateien bleiben
unverändert vorhanden. Testkopien können aus ihnen erneut erzeugt werden.
