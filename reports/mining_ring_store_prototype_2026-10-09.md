# Regionaler lokaler Ringspeicher: Prototyp und Vergleich

Stand: 9. Oktober 2026. Beauftragt waren ein isolierter Prototyp und der
250-/500-LY-Vergleich. Die native App verwendet weiter ihren bisherigen Speicher.

Der Prototyp senkt im kontrollierten Offline-Vergleich den RAM nach dem
Ringzugriff um rund 69 % bei 250 LY und 52 % bei 500 LY. Der erste Ringzugriff
ist rund 77 % beziehungsweise 61 % kürzer. Alle geprüften Ergebnisse sind
identisch. Das ist ein belastbarer Grund, eine spätere Integration vorzubereiten;
eine Umstellung bestehender Benutzerdateien wurde damit nicht vorgenommen.

## Messwerte

Median aus je drei frischen Prozessen pro Variante und Radius, seriell mit
wechselnder Reihenfolge. Beide Varianten verwenden dieselbe speichersparende
Katalogdarstellung: geteilte Feldnamen/Faktentexte und interne Array-Snapshots.
Alle Payloads auf Platte sind unkomprimiert. Der Betriebssystem-Dateicache wurde
nicht geleert; dies ist keine Messung eines kalten Datenträgers.

| Messpunkt | JSON 250 LY | SQLite 250 LY | JSON 500 LY | SQLite 500 LY |
| --- | ---: | ---: | ---: | ---: |
| In RAM geladene Ringe | 391.212 | 53.545 | 391.212 | 120.157 |
| Tatsächliche regionale Ringe | 53.545 | 53.545 | 120.157 | 120.157 |
| Ring öffnen und Region auswählen | 5,63 s | 1,29 s | 5,67 s | 2,22 s |
| Prozess-RAM nach Ringzugriff (Working Set) | 433,9 MiB | 136,5 MiB | 434,8 MiB | 209,9 MiB |
| Private Commit nach Ringzugriff | 416,4 MiB | 118,4 MiB | 417,2 MiB | 192,0 MiB |
| Prozess-RAM nach kompletter Vergleichsmatrix | 620,4 MiB | 319,4 MiB | 639,1 MiB | 414,6 MiB |
| Peak Working Set im Vergleich | 825,2 MiB | 524,6 MiB | 1.125,8 MiB | 899,9 MiB |

Der Ringzugriff umfasst JSON-Laden plus regionale Auswahl beziehungsweise
Store-Prüfung plus SQLite-Auswahl und Dekodierung. Ergebnis-Hashing und
anschließende Filter-/Routenberechnung zählen nicht zu dieser Zugriffszeit.
Die Zeitspannen der drei Läufe waren 5,60–5,65 / 1,289–1,297 s bei 250 LY
und 5,63–5,69 / 2,21–2,28 s bei 500 LY.

Das sind lokale Python-/Domain-Messungen mit Qt-Modulen, ohne laufende Oberfläche.
Sie messen weder die installierte EXE noch Netzwerk, Rendering, Eingabelatenz
oder die gesamte erste Live-Suche. Markt- und Powerplaydaten werden weiterhin
über ihre vorhandenen Wege geladen und bewertet.

Bereits warme Platinum-Planungen ändern sich wenig: ACQUIRE liegt bei 250 LY
bei 0,288 / 0,285 s und bei 500 LY bei 0,899 / 0,884 s. Die breite
ALL-COMMODITIES-Aufbereitung braucht weiterhin etwa 7 s bei 250 LY und 16 s
bei 500 LY. Die erste REINFORCE-Berechnung ist im SQLite-Replay etwas langsamer;
der Gewinn des Pakets entsteht durch weniger globale Ringdaten beim Erstzugriff.
Es gibt deshalb kein Versprechen, jede spätere Berechnung erheblich zu beschleunigen.

## Umsetzung

- `tools/mining_ring_store_prototype.py`: separater, von der App nicht verwendeter
  Store. Streaming-Übernahme der eingefrorenen Testkopie, vollständige Original-
  Payloads als TEXT, Quellreihenfolge und Root-Metadaten erhalten. Keine
  Deduplizierung, Kürzung, Altersbereinigung oder Löschung von Quelldateien.
- Räumlicher SQLite-RTree, Systemnamenindex und konservative Koordinatenbox;
  anschließend dieselbe auf 0,1 LY gerundete inklusive Entfernungsregel.
  Zeilen mit ungeeigneten/nichtendlichen Koordinaten bleiben gespeichert und
  werden entsprechend den vorhandenen Auswahlregeln behandelt. Kein Zeilenlimit.
- SQLite-Leser öffnen nur lesend, prüfen Format und synthetisches Profil/
  Generation in einer Lesetransaktion und begrenzen den Page Cache auf 4 MiB.
  Ein Aufbau wird erst nach vollständiger Transaktion und Quellhashprüfung
  atomar unter einem neuen Dateinamen verfügbar. Vorhandene Ziele werden abgelehnt.
- Die vorhandenen Filter, Quellenzeiten, Frische-, Ertrags-, Preis- und
  Meritregeln laufen weiterhin im bestehenden Domain-Code. Der Store gibt
  ursprüngliche Fakten zurück und erzeugt keine neue Verifizierung.
- `tools/benchmark_mining_ring_store.py`: Offline-Runner mit getrennten Prozessen,
  festen Uhren für Ring-/Routenbewertung, anonymen öffentlichen Testkopien,
  HTTP-Sperre und isolierten Laufzeitverzeichnissen.

Wichtig: Die Messung verwendet `--compact`, entsprechend
`nearby(..., snapshot_arrays=True)`. Gewöhnliche unabhängig dekodierte JSON-Dicts
verbrauchen im 500-LY-Fall mehr RAM als der bestehende optimierte JSON-Loader.
Die bestehende sparsame Darstellung muss bei einer Integration mit übernommen
werden. Sie ändert keine Fakten und komprimiert keine vorhandene Datei.

## Integrität und Ergebnisgleichheit

Alle **391.212 Ring-Payloads** wurden zeilenweise in ursprünglicher Reihenfolge
gegen die JSON-Testkopie verglichen, einschließlich unbekannter Zusatzfelder,
eingebetteter Quellenbeobachtungen und alter Beobachtungszeiten. Root-Metadaten,
SQLite-Integritätsprüfung und RTree-Integritätsprüfung stimmen ebenfalls.

Payload-/Reihenfolge-SHA256:
`bb290725229eb54fdd5eba0815f9332d3a29ef30ccf49207659e0293f41da0d4`.

Pro Radius und in jedem Wiederholungslauf identisch:

- vollständige regionale Originaldaten ohne Abschneiden;
- sieben Filterkombinationen: Laser, Pristine, Major, bestätigte Evidenz,
  Recheck, Void Opals/Core und alle Commodities, einschließlich Belt-/Ringfilter;
- jeweils 100 vollständige Routen samt Reihenfolge und sämtlichen Ergebnisfeldern
  für REINFORCE, ACQUIRE und HIGHEST PROFIT;
- Recheck-Resultate und ACQUIRE-Routen bei um zwei Tage fortgeschrittener Uhr.
  Die Bewertung verändert sich dabei tatsächlich; gespeicherte Daten frieren
  Alter oder Eignung nicht ein.

**44 relevante Tests grün**, darunter neun neue Store-Vertragstests. Diese
prüfen unter anderem Rundungsgrenzen, Unicode/BOM/Chunkgrenzen, fehlende und
nichtendliche Koordinaten, Datenverlust bei fehlerhaften Eingaben, unabhängige
parallele Leser, Scope-Fences und unabhängige verschachtelte Fakten.
Syntaxprüfung, Repository-Hygiene samt neuen Dateien und Whitespace-Prüfung
sind bestanden. Produktionsdateien wurden nicht geändert; ein erneuter
Windows-Build oder QML-Gesamttest ist für diese isolierten Tools nicht erfolgt.

## Plattenbedarf und Grenzen

Der einmalige Aufbau der Testdatenbank dauert hier 9,97 s bei 38,1 MiB Peak RAM.
Die neue Datenbank einschließlich Indizes belegt **434,46 MiB**, zusätzlich zum
erhaltenen JSON von rund 331,19 MiB. Diese Übernahme wurde ausschließlich an
einer eigens erstellten Testkopie durchgeführt.

Der Prototyp ist ein unveränderlicher Offline-Bestand. Laufende atomare
Zusammenführungen neuer Server-/Journalbeobachtungen, Historienarchivierung,
Profilwechsel/Reset/Shutdown im Controller, Systemvorschläge und dynamische
regionale UI-Publikation sind noch nicht integriert. Die statische Scope-Prüfung
ersetzt diese erforderlichen Controller-Fences nicht. Historien-Datenbanken
wurden nicht übernommen oder geändert.

Originaldateien und alle vier öffentlichen Eingabedateien bleiben bei gleichen
Prüfsummen erhalten. Auch die wiederverwendete Testdatenbank hat nach dem Replay
dieselbe Prüfsumme. BGS-Prognosen, installierte Benutzer-App, Server, Migrationen,
Release und Git-HEAD wurden nicht verändert. Der Prototyp ist lokal uncommitted.

## Reproduktion und Artefakte

Erster Lauf mit normalen SQLite-Dicts und einmaligem Store-Aufbau:
`.test-tmp/ring-store-prototype-20261009-01/`.
Maßgeblicher Vergleich mit der sparsameren Darstellung und derselben eingefrorenen
Eingabe/Datenbank: `.test-tmp/ring-store-prototype-20261009-02/result.json`.
Separate Mess-JSONs und Logs liegen in diesen Verzeichnissen; Testlog:
`.test-tmp/ring-store-unit-20261009/tests.log`.

```powershell
.venv/Scripts/python.exe -B tools/benchmark_mining_ring_store.py `
  --prepared .test-tmp/ring-store-prototype-20261009-01 `
  --output .test-tmp/ring-store-prototype-new-replay --compact --trials 3
```

Das Ausgabeziel muss neu sein. `--prepared` liest die geprüften Testdaten,
ohne einen zweiten großen Datenbestand anzulegen. Der Runner speichert
Eingabe- und Code-Prüfsummen sowie sämtliche Ergebnis-Prüfsummen.

Ein nächster Arbeitsschritt wäre die Integration eines regionalen Readers mit
verlustfreier laufender Aufnahme neuer Fakten und den vorhandenen Controller-
Fences. Die Übernahme echter bestehender Benutzerbestände bleibt eine separat
abzustimmende Aktion; altes JSON und vorhandene Historien sollen erhalten bleiben.
