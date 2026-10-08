# MiningFinder: gebündelte Planung und wiederverwendeter Powerplay-Index

8. Oktober 2026. Umsetzung der nächsten beiden Performance-Schritte nach
der 100-Routen-Messung. Noch kein Commit, Release oder Serverdeployment.

## Ergebnis

Unnötige Zwischenplanungen wurden reduziert; der Powerplay-Rohindex wird
bei unveränderten Quellen wiederverwendet. Im isolierten Live-Kontrolllauf
brauchte die Folgesuche bis zur letzten Listenänderung **19,5 statt 25,6 s**.
Die erste lokale Liste erschien nach **2,1 s**. Die komplette Erstsuche wurde
jedoch nicht schneller: Der regionale Ringabruf dauerte diesmal länger.

**Keine RAM-Verbesserung:** Der Rohindex bleibt für die Wiederverwendung im
Speicher. Die gemessene Spitze einschließlich Tabtest stieg von 1.309,0 auf
1.400,8 MiB. Umfang und Zustand der Live-Daten änderten sich ebenfalls;
der Mehrbedarf lässt sich nicht vollständig dem Cache zuschreiben.
Einzelne UI-Pausen sind weiterhin vorhanden.

## Funde und Änderungen

1. Regionale Sync-, Merge- und Projektionsmeldungen lösten Planungen gegen
   noch unvollständige Zwischenstände aus. Jetzt bleibt das letzte Ergebnis
   derselben Suche sichtbar, bis diese zusammengehörige Arbeit abgeschlossen
   ist. Die schnelle erste lokale Planung bleibt erhalten. Eine neue Suche
   oder ein anderes Profil übernimmt keine Ergebnisse der alten Anfrage.
2. Jede Planung baute denselben Powerplay-Index erneut auf. Ein gesperrter
   Ein-Eintrag-Cache verwendet ihn jetzt bei identischen Quell-Snapshots,
   Profilen und Dateipfaden wieder. Neue Snapshots ersetzen den Eintrag;
   Profilwechsel erhalten eine eigene Instanz. Es gibt keine zusätzliche
   Datei und keine Sammlung alter Indexgenerationen im Cache.
3. Der Busy-Zustand berücksichtigt auch aufgeschobene Planung, solange deren
   Eingaben tatsächlich bearbeitet werden. Wiederholungs-/Relay-Puffer
   halten die Suche dagegen nicht dauerhaft beschäftigt. Dadurch beginnt die
   Nachprüfung nicht auf einem bekannt veralteten Zwischenstand.

Ranking, Filter, Altersprüfung, unbekannte Fakten und Prüfbudgets bleiben
unverändert. Gespeichert wird nur der Rohindex, keine zeitabhängige Bewertung.
CHECKING-/Abschlussmeldungen der gezielten Prüfung bleiben erhalten.
Beliebig in-place veränderbare synchrone Testeingaben nutzen den Cache nicht.

## Messung vor / nach Änderung

Vergleich mit `mining_post_reuse_100_2026-10-08.md`. Gleiche Suchparameter:
Shanteneri, Platinum/Laser, Powerplay Merits, Aisling Duval/Reinforce,
250 LY, 100 Treffer, Large Pad, Nachfrage 5.000–500.000 t, Marktalter 1 h.

| Messgröße | Erstsuche vorher → jetzt | Folgesuche vorher → jetzt |
| --- | ---: | ---: |
| Planungsaufrufe | 8 → 4 | 5 → 3 |
| Kumulierte Planungslaufzeit | 14,886 → 5,205 s | 10,933 → 3,622 s |
| Powerplay-Indexaufbauten | 8 → 2 | 5 → 1 |
| Davon Indexlaufzeit | 5,366 → 1,124 s | 2,803 → 0,553 s |
| Neue Listenveröffentlichungen | 6 → 4 | 4 → 3 |
| Erste sichtbare Liste | 3,232 → 2,107 s | jeweils 0,003 s, vorherige Liste |
| Letzte Listenänderung | 58,250 → 65,384 s | 25,587 → 19,522 s |
| Regionaler Ringabruf | 37,260 → 49,665 s | 0,603 → 0,182 s, Cachetreffer |

Planungszeiten sind Hintergrund-Laufzeiten, nicht reine CPU-Zeit. Die
Indexzeit ist darin enthalten. Die Folgesuche war in diesem Lauf rund 24 %
früher ruhig; das ist keine garantierte Beschleunigung jeder Suche.
Live-Daten, Serverlast und Ringbestand waren zwischen den Läufen verschieden.

Alle Veröffentlichungen hatten 100 Zeilen, ohne zwischenzeitliche Leerung.
Die Mining-Reihenfolge blieb im neuen Lauf stabil. Preise, Verkaufsdaten und
Prüfstatus wurden weiterhin ergänzt. Die Erstprüfung begann nach 58,406 s
und endete nach 64,473 s; die Folgeprüfung lief von 13,024 bis 18,618 s.
Mit zusätzlichen drei Sekunden Ruhe: 68,396 bzw. 22,529 s.

Die erste Prüfung erledigte 37 deduplizierte Powerplay- und sechs Marktziele.
Für die 37 Systeme kam kein aktueller Powerplay-Beleg zurück. Am Ende waren
vier Routen VERIFIED; 96 von 100 Routen hatten weiterhin unbekannte
Powerplay-Eignung. Fehlende Daten werden nicht durch Wiederverwendung wahr.
Die Folgesuche erledigte sechs neue Marktziele plus sechs bereits gecachte
Prüfungen. Das bedeutet ausdrücklich nicht 100 vollständig geprüfte Routen.

## Bedienbarkeit, Speicher und Grenzen

- Qt-Timer mit 10-ms-Intervall: p95 11,1 ms in der Erstsuche, 11,8 ms in der
  Folgesuche. Größte Pause jeweils rund 607 ms; während des Tabtests 1.313 ms.
  Normale Reaktion verbessert sich nicht automatisch an jedem Engpass.
- 45 Tabwechsel während eines zusätzlichen Syncs und seiner Nacharbeit:
  Operations Median 32 / Maximum 117 ms, Materials 129 / 221 ms,
  Engineering 39 / 46 ms, CMDR 32 / 70 ms, MiningFinder 33 / 926 ms.
  Gemessen bis zur sichtbaren QML-Seiteninstanz, nicht bis zum fertigen Bild;
  CMDR ohne echte Flottendaten.
- RSS: Startbereitschaft 950,4 MiB, nach beiden Suchen 1.270,7 MiB;
  Spitze einschließlich Tabtest 1.400,8 MiB. Der Speicherbedarf bleibt zu hoch.
- Der Powerplay-Reuse-Zeitraum war nach der langen Erstsuche abgelaufen:
  Die Folgesuche lud korrekt 60 regionale Powerplay-Seiten neu, rund 5,2 s.
  Keine Freshness-Grenze wurde verlängert, um Messwerte zu verbessern.

Noch offen: großflächige Katalog-/Merge-/Projektionsarbeit und dauerhaft
gehaltene Ringdaten, kleinere regionale Serverantworten sowie der separat
gewünschte koordinierte Abschluss mit einmaliger finaler Ergebnisfreigabe.
Der jetzige Schritt reduziert Zwischenarbeit, beseitigt Nachladen aber nicht.
BGS-Prognosen wurden nicht verändert.

## Prüfung und Reproduzierbarkeit

- Gesamte Testsuite: **1.157 Tests erfolgreich**, 136,153 s.
- Elf neue Regressionstests: Bündelung, Profil-/Suchwechsel, aufgeschobener
  Busy-Zustand, Retry-Puffer, Prüfprogress, Quellwechsel, Parallelzugriff
  sowie exakte Ergebnisgleichheit mit/ohne Index über Modi und Altersgrenzen.
- Repository-Hygiene und `git diff --check` erfolgreich.
- Echte Controller, Worker und QML-Seiten, Python 3.13.15 / PySide6 6.11.2,
  offscreen/Software, 1600 × 1000. Nicht die installierte EXE; keine Messung
  realer Maus-bis-Bild-Latenz. Startbereitschaft nach 5,901 s.
- Öffentliche Katalogkopie: 334.669 Ringe, 150.000 Märkte, 91.575
  Powerplay-Katalogzeilen plus öffentliche Beobachtungen. Synthetischer
  Commander; nur öffentliche GETs, Uploads gesperrt. Keine Netzwerk- oder
  QML-Fehler. State-Finds-Startsync lief mit.
- Rohdaten samt Quellhashes:
  `.test-tmp/mining-plan-coalesced-100-20261008/result.json`;
  Kopierinventar: `source-inventory.json` im selben Verzeichnis.
- Nach Prozessende wurden ausschließlich die selbst erzeugten
  Katalog-/Journal-Testkopien entfernt, rund 2,03 GiB. Rohdaten und Inventar
  bleiben erhalten. Bestehende AppData-Dateien wurden weder verändert noch
  gelöscht; keine reale App neu gestartet oder beendet.
