# Paket 1: lokale Mining-Katalogverarbeitung

Stand: 2026-10-09. Implementiert und lokal getestet; noch nicht committed,
veröffentlicht oder in die installierte App übernommen. Keine Serveränderung.

## Ergebnis

Wiederholte lokale Planungen derselben 250-LY-Region brauchen im kontrollierten
Replay ungefähr ein Drittel der bisherigen Zeit. Preise, Nachfrage, Merit-Regeln,
Alter und Ergebnisreihenfolge bleiben unverändert. BGS wurde nicht angefasst.

| Lokaler Arbeitsschritt | Vorher | Nachher | Einordnung |
| --- | ---: | ---: | --- |
| Erste Planung, 250 LY | 0,839 s | 0,743 s | Einzelmessung einschließlich neuer Umkreisauswahl |
| REINFORCE, 250 LY | 0,845 s | 0,287 s | Median aus drei Wiederholungen; 66,1 % weniger Zeit |
| ACQUIRE, 250 LY | 0,844 s | 0,286 s | Median; 66,1 % weniger Zeit |
| HIGHEST PROFIT, 250 LY | 0,845 s | 0,285 s | Median; 66,3 % weniger Zeit |
| ACQUIRE, 500 LY | 1,328 s | 0,894 s | Median; 32,7 % weniger Zeit, Region überschreitet Indexlimit |
| Ring-Merge einschließlich dauerhafter Historien | 3,606 s | 3,483 s | Median; kleiner Gewinn von 3,4 % |

Das sind Zeiten der lokalen Python-Verarbeitung, **keine Gesamtsuchzeiten**.
Netzwerk, regionale Downloads, SQLite-Marktabfrage, Katalogstart und Rendering
sind nicht Bestandteil dieser Offline-Messung. Der Merge-Probe verwendet die
öffentliche Helper-Standardeinstellung ohne Transient-Field-Bereinigung;
der Produktionspfad mit Bereinigung ist zusätzlich durch Regressionstests geprüft.

## Funde und Fixes

1. **Wiederholter vollständiger Entfernungslauf:** Die Suche prüfte auch nach
   bloßen Preis-/Powerplay-Änderungen erneut alle Ringkoordinaten. Ein kleiner,
   arbeitsthread-seitiger Umkreisindex speichert jetzt ausschließlich Positionen
   im unveränderten Quellbestand und die geometrische Entfernung. Kein Preis,
   keine Freischaltung, kein Alter, keine Ertrags- oder Merit-Bewertung wird darin
   gespeichert.
2. **Teure Arbeit an weit entfernten Ringen:** Eine konservative Koordinatenbox
   vermeidet unnötige Quadratwurzelberechnungen. Anschließend gilt unverändert
   die bisherige exakte Entfernung, auf 0,1 LY gerundet, mit inklusiver Radiusgrenze.
   Belt-Prüfungen werden erst innerhalb der passenden Region ausgeführt.
3. **Gleiche Methoden-/Ring-Typ-Prüfung pro Ring:** Zulässige Ringtypen werden
   einmal pro Suchanfrage berechnet, statt zigtausendmal dieselben Regeln
   aufzubereiten.
4. **Unnötige Rekursion und Bereinigung:** Snapshot-Erstellung und stabile
   Historienidentitäten besuchen einfache Zahlen/Textwerte nicht mehr mit einem
   zusätzlichen Funktionsaufruf. Der abschließende Bereinigungslauf entfällt,
   wenn keine Felder zu entfernen sind. Ansonsten erfolgt die Feldprüfung ohne
   einen neuen Python-Generator pro Ring.

## Sicherheits- und Speichergrenzen

- Ein Umkreisindex, höchstens 100.000 Positionen/Entfernungen, unter 2 MiB
  Indexspeicher. Dazu kommt die Referenz auf den bereits vorhandenen Quellbestand;
  keine weitere tiefe Katalogkopie und kein zusätzlicher Festplattenindex.
- Größere Regionen werden vollständig gestreamt, nicht abgeschnitten oder
  heimlich auf einen kleineren Suchradius reduziert.
- Neue Quellliste, Ursprung oder Radius machen den Index ungültig. Neue
  Projektionen, Profilwechsel, Dateipfadwechsel, Reset und expliziter Refresh
  ersetzen beziehungsweise verwerfen ihn. Ein alter Worker bleibt an seinen
  eigenen Snapshot gebunden.
- Publikations-/Revisionsprüfungen für asynchrone Ergebnisse bleiben bestehen.
- Preise und Merit-Eignung werden weiter mit aktuellen Eingaben bewertet;
  Beobachtungszeitpunkte werden nicht verlängert. Der bestehende Minuten-Takt
  der Suchansicht bleibt unverändert.
- Historien werden weiterhin dauerhaft geschrieben. Bei Schreibfehlern werden
  Rohbeobachtungen weiterhin verlustfrei zurückgehalten.
- Bestehende AppData-Dateien wurden weder verändert, gelöscht noch komprimiert.
  Entfernt werden nur die für diesen Vergleich erzeugten Katalogkopien und
  Test-Historien; Messprotokolle bleiben erhalten.

## Nachweis

Fester öffentlicher Testbestand: 391.212 Ringkandidaten, 736 regionale
Marktbeobachtungen sowie die kopierten öffentlichen Powerplay-Kataloge.
Feste Spielzeit: 2026-10-09 12:00 UTC. Vorher: Quellstand von Release 1.5.42
(`8bc47bbb58f6312a8558d89e886d7e0ce0955668`), nachher: diese lokalen Änderungen.
Keine Netzwerkzugriffe im Replay. Die vier Eingabedatei-Hashes stimmen überein.

Alle vier Suchfälle liefern jeweils dieselben 100 vollständigen Ergebniszeilen
in derselben Reihenfolge. SHA-256-Prüfsummen aller Ergebnisfelder stimmen
vorher/nachher überein. Auch alle 391.212 zusammengeführten Kandidaten sowie
die Nutzdaten beider Historienkategorien sind identisch:

- Merge: `2328bc8e5bede9c8c8c0c6f2117b445b53810f28cedf40ad5217a840283375aa`
- `mining_catalog`: 24.456 historische Datensätze.
- `mining_observations`: 24.456 historische Datensätze.
- Beide Historien-Nutzdaten: `582b5ebb377e836fcdaded1bbc7332b343b7ce3126c505913134fd210524c907`.

Messwerkzeug: `tools/benchmark_mining_local.py`.
Protokolle: `.test-tmp/mining-local-before-20261009-02/result.json` und
`.test-tmp/mining-local-after-20261009-02/result.json`.

Validierung:

- 1.213 App-Tests erfolgreich, einschließlich 13 neuer Regressionstests.
- Vollständiger nativer Offscreen-QML-Smoke: PASS für alle Seiten, Dialoge
  und Overlays, einschließlich MiningFinder und Engineering.
- Repository-Hygiene und `git diff --check`: erfolgreich.
- Neue Tests prüfen Rundungsgrenzen, ungültige/fehlende/nichtendliche
  Koordinaten, mehrere Filter und Methoden, Profile/Pfade/Resets, konkurrierende
  Worker, Speicherlimit, fortschreitende Frische und verlustfreie Archivfehler.

## Verbleibende Hebel

Die Ring-Vorbereitung bleibt wegen Normalisierung und dauerhafter Historien ein
messbarer Kostenpunkt. Netzwerk- und Startzeit werden durch diese Änderung nicht
beseitigt. Als nächstes folgt laut Fahrplan Paket 2: bedarfsgerechtes Laden beim
Start und weniger gleichzeitig gehaltene große Katalogansichten. Keine
pauschale Cache-Löschung und keine Entfernung historischer Nutzdaten.
