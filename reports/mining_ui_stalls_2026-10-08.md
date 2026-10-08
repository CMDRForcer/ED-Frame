# Mining Finder: gemessene UI-Pausen und Fixes

8. Oktober 2026. Lokaler Quellstand, kein Commit, Push, Release, Deployment
oder Neustart der installierten App. Vorhandene Originaldateien bleiben erhalten.
BGS-Prognosen, Datenumfang, Offline-Funktionen, Ranking, Filter, Aktualität und
Netzwerk-Prüfbudgets wurden nicht verändert.

## Befunde und Änderungen

1. **Powerplay-Merge noch im UI-Thread.** `_publish_mining_powerplay` brauchte
   im Erstsuchlauf 783 ms; der gesamte Abschluss-Slot 981 ms. Der Merge einer
   großen Region, sein vollständiger Gleichheitsvergleich und die Vorbereitung
   der neuen Fakten laufen jetzt auf einem erfassten Hintergrund-Worker.
   Die UI veröffentlicht nur eine vorbereitete, zur exakten Ausgangsliste
   passende Version. Bei gleichzeitig eintreffenden Relay-Fakten wird vor der
   Veröffentlichung erneut im Worker zusammengeführt. Die ursprüngliche
   Anfrage bleibt dabei aktiv; Märkte/Benachrichtigungen werden nicht vor den
   zugehörigen Powerplay-Fakten veröffentlicht. Anfrage-, Profil-, Generation-
   und Pfadprüfungen greifen erneut beim Abschluss. Gezielte Verifikation nutzt
   denselben Pfad; Shutdown/headless und Fehler behalten den synchronen Fallback.

2. **Speicherbereinigung blockiert auch Hintergrundarbeit.** Generation-2-GC
   hielt den Python-Interpreter im Vorher-Lauf bis zu 600 ms an. Lange erhaltene
   Mining-Fakten speichern verschachtelte Arrays jetzt intern als Tupel. Leere
   und skalare Tupel sowie Blatt-Dicts kann CPythons normale GC aus der laufenden
   Traversierung nehmen. Nicht alle Container werden dadurch GC-frei; insbesondere
   Tupel mit veränderbaren Dicts können weiter verfolgt werden.
   Root-Zeilenlisten und normale Dicts bleiben bestehen. Der generische JSON-Lader
   bleibt unverändert nutzbar; nur private Mining-Snapshots verwenden diese Option.
   Ausgewählte Ansichten werden in unabhängige normale Dicts/Listen zurückkopiert.
   JSON-Dateien, Originalbeobachtungen und Archiv-Identität bleiben gleich.
   Es gibt kein `gc.disable`, `gc.freeze`, geänderte GC-Schwellen oder native
   Eingriffe in die Speicherverwaltung.

3. **Mehrfache Journal-Dateimetadatenabfragen im UI-Timer.** Der EDDN-Profilcheck
   fragte die Journal-Metadaten direkt und nochmals über Location-/Cacheprüfungen
   ab. Er verwendet jetzt einmalig denselben aktuellen Schlüssel für alle diese
   Prüfungen, ebenso beim Upload-Baseline-Check. Kein zeitlicher Zusatzcache und
   keine abgeschwächte Profilprüfung. Diese letzte kleine Änderung ist durch
   Regressionstests abgesichert, nicht separat live vermessen.

## Kontrollierter Vergleich: identische öffentliche Ringdatei

Getrennte CPython-3.13.15-Prozesse; 343.964 Zeilen. Identische Datei, feste
Bewertungszeit, 24.455 verteilte Merge-Zeilen und echtes SQLite-Historienarchiv.
Der Vergleich isoliert normale verschachtelte Listen gegen private Snapshots;
das vorher bereits eingeführte Dict-/String-Sharing bleibt in beiden Läufen an.

| Messgröße | Listen | Snapshots |
| --- | ---: | ---: |
| Laden | 4,4078 s | 4,6301 s |
| RSS nach Laden | 453,4 MiB | 355,5 MiB |
| Vollständige GC, vier Messungen | 189–200 ms | 102–106 ms |
| Merge einschließlich Historie | 3,5841 s | 3,9251 s |
| RSS nach Merge | 569,9 MiB | 464,1 MiB |
| RSS-Spitze bis Mergeende | 621,9 MiB | 523,8 MiB |

Rund 98–106 MiB weniger RAM, ungefähr halbierte GC-Zeit in diesem isolierten
Versuch. Nachteil: etwa 0,22 s zusätzliches Laden und 0,34 s zusätzlicher Merge.
Mehr CPU für die private Repräsentation, keine zusätzliche Netzabhängigkeit.

Quelldigest und geladener JSON-Digest in beiden Läufen:
`d8976335f05afbe3184bdbf27f480cd821ed50aefb5449a50eb7c75b4e65d957`.
Gemergter Gesamtdigest in beiden Läufen:
`0d88f705b9ced7f2a2a391ba387ddecb5b1d05b658a2956de3eaaec075da0aac`.
Eingehende Fakten unverändert; beide Archive ohne Fehler, Zeilenanzahl erhalten.

## Echte Controller/QML mit öffentlichen Serverabfragen

Offscreen-Softwaredarstellung, 1600 × 1000; synthetischer Commander,
separate öffentliche Profilkopien, nur erlaubte GETs, alle Uploads gesperrt.
Shanteneri, Platinum/Laser, Powerplay Merits/Aisling Duval/Reinforce, 250 LY,
100 Ergebnisse, Large Pad, Nachfrage 5.000–500.000 t, Marktalter 1 h.
Vorher 343.964, nachher 345.594 lokale Ringe, jeweils 150.000 Märkte und
91.575 Powerplay-Katalogzeilen. Live-Daten und Serverlast sind nicht identisch;
die Zahlen sind Beobachtungen, keine garantierten Laufzeiten oder ein reiner A/B-Test.

| Messgröße | Vorher | Nachher |
| --- | ---: | ---: |
| RSS bei Startbereitschaft | 739,0 MiB | 634,9 MiB |
| RSS-Spitze einschließlich Tabtest | 1.201,8 MiB | 1.061,5 MiB |
| Startbereitschaft | 6,715 s | 7,062 s |
| Erste lokale Liste | 2,244 s | 2,678 s |
| Erstsuche vollständig abgearbeitet | 53,609 s | 53,685 s |
| Folgesuche vollständig abgearbeitet | 24,689 s | 23,591 s |
| Max. Qt-Timerlücke Erstsuche | 1.126 ms | 418 ms |
| Max. Qt-Timerlücke Folgesuche | 621 ms | 378 ms |
| Powerplay-Veröffentlichung Erstsuche, UI | 783 ms | 13 ms |
| Max. Qt-Timerlücke bei Tabwechseln/Sync | 637 ms | 1.042 ms |
| Langsamster Tab bis QA-Objekt bereit | 1.198 ms | 2.320 ms |

Keine QML-Diagnosefehler, jeweils 45 Tabwechsel. Alle Listenveröffentlichungen
hatten 100 Zeilen; keine Ergebnisleerung. Nachher 47/47 Erstprüfungen und 12/12
Folgeprüfungen abgeschlossen. Das ist keine Behauptung über 100 vollständig
verifizierte Routen: fehlende Powerplay-Fakten und alte Märkte bleiben unbekannt.

**Kein pauschaler Responsiveness-Sieg:** Erst- und Folgesuche haben kürzere
Maximalpausen; die eigentlichen Serverwartezeiten sind kaum verändert.
Der längste Tabwechsel war im Nachher-Lauf schlechter. Diese Ausreißer
werden nicht durch Durchschnittswerte oder die RAM-Ersparnis verdeckt.

## Verbleibende Baustelle

Ein zusätzlicher reiner Tab-/Sync-Diagnoselauf reproduzierte einen Materials-
Wechsel mit 2,303 s, während Ring-Merge und vollständiges Katalogspeichern
gleichzeitig liefen. Die maximale einzelne Qt-Timerlücke lag bei 534 ms.
Stack-Sampling zeigte im UI-Timer `pollJournal` unter anderem in
`_poll_surface_nav` → `read_json` → Windows-Pfadauflösung und in
`_sync_eddn_profile` → Journal-Metadaten → `mkdir`. Andere Proben zeigten
nur die native Qt-Ereignisschleife, während Python-Merge/Serializer liefen.

Damit sind synchrone Datei-Polls während starker Schreiblast ein konkret
beobachteter weiterer Engpass, aber nicht als alleinige Ursache sämtlicher
2,3 Sekunden bewiesen. Die mehrfachen Profil-Metadatenlesungen sind reduziert;
die übrigen Status-/Journal-Polls sind noch nicht vollständig workerbasiert.
Nächster Hebel: diese Polls mit Anfrage-/Profil-/Pfadfences auf Worker verlegen
und QML-Inkubation unter Merge-/Schreiblast separat messen. Keine Datenkürzung.

## Prüfbarkeit und temporäre Dateien

- Vollständige Testsuite: **1.172 Tests erfolgreich**, 135,704 s, einschließlich
  QML-Tests. Repository-Hygiene und `git diff --check` erfolgreich.
- Neue Regressionen für Snapshot-/JSON-/View-Gleichheit, unabhängig veränderbare
  Ansichten, normale GC, unveränderte Merge-Eingaben und Historie, Archivfehler-
  Rückfall, leere Powerplay-Koordinaten, konkurrierende Fakten, Busy-/Publikations-
  Reihenfolge, Profilwechsel während Vorbereitung und einmalige Metadatenabfrage.
- Alle getesteten Suchmodi werden zusätzlich mit privaten Snapshot-Eingaben
  gegen die bisherige dekorierte Projektion verglichen.
- Rohmessungen: `.test-tmp/mining-ui-profile-before-20261008/`,
  `.test-tmp/mining-ui-profile-after-20261008/` und
  `.test-tmp/mining-ui-tabs-diagnostic-20261008/`, jeweils `result.json` und
  `source-inventory.json`; kontrollierte `layout-lists.json`/`layout-snapshots.json`
  im ersten Verzeichnis.
- Diagnosewerkzeug: `tools/benchmark_mining_baseline.py --profile-ui`, optional
  `--tabs-only`; zusätzlich `tools/benchmark_catalog_layout.py --mode snapshot`.
- Nach Prozessende nur die selbst erzeugten Testprofil-/Journalkopien und zwei
  Vergleichsarchive entfernt: 6,175 GiB. Rohmessungen und Inventare bleiben erhalten.
  Original-AppData, bestehende Historie und Nutzerdateien wurden nicht gelöscht.
