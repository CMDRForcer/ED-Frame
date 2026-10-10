# Adaptive Lastverteilung – lokaler Entwicklungsstand, 10.10.2026

Historischer Zwischenstand vor dem Rollout. Veröffentlichung und abschließende
Prüfung: [Bericht für 1.0.8](mining_merit_rollout_2026-10-10.md).

ED-Frame verteilt große Rechenaufgaben über einen gemeinsamen Prozesspool und
begrenzt die übrige Hintergrundarbeit. Die Änderungen bauen auf der lokalen
Entkopplung von UI und Datenabgleich auf. Basis: Commit
`5dea25fbb3ea7bfc679b3043d7099c036bf68a82`, Versionsressource **1.0.7**.
Dieser Stand ist lokal, uncommitted und unveröffentlicht.

## Was die App jetzt verteilt

| Bereich | Verhalten |
|---|---|
| Mining | Bestehende lesende Berechnung verwendet den gemeinsamen Rechendienst |
| Große Journale | Ab 20.000 Ereignissen werden Powerplay, Fahrzeug/SRV, Missionen, Community Goals und Exploration gemeinsam ausgelagert, sofern zwei Rechenplätze verfügbar sind |
| Kleine oder ausgelastete PCs | Journal-Auswertungen bleiben im eigenen Hintergrundthread mit den bestehenden Caches, damit sie nicht auf eine lange Mining-Suche warten |
| Große Powerplay-Bestände | Zusammenführung ab 20.000 Eingangszeilen im Rechendienst; dieselben Regeln und Reihenfolgen |
| Commander | Die bereits schnelle, vorberechnete Darstellung bleibt im Hintergrundthread |
| Journal, Suche, Frontier, Export, Katalog | Gemeinsame Begrenzung der koordinierten Hintergrundthreads, mit eigener Journal- und Suchkapazität |
| Datenabfragen und Routenprüfung | Auch ihre untergeordneten Netzwerkpools berücksichtigen Prozessorzahl, freien RAM und CPU-Auslastung |
| Lokale Bestandsstatistik | Zählen von Warenzeilen und Stationsinventaren erfolgt beim Start und Profilwechsel im Hintergrund; Qt übernimmt vier fertige Zahlen |

Schreibvorgänge, Profilverwaltung, Archivierung und Qt-Objekte werden nicht in
Rechenprozesse verschoben. Der neue Rechendienst erhält nur reine Berechnungen
oder lesende Mining-Abfragen. Profil- und Ergebnisrevisionen bleiben geprüft.
Alte oder inzwischen überholte Bestandszählungen überschreiben keine neueren
Zahlen eines anderen Profils oder Imports.

## Automatische Grenzen und Kompatibilität

- Höchstens **zwei gleichzeitig zugelassene Rechenaufgaben**. Unter vier
  logischen Prozessoren, bei unbekannten Speicherwerten, weniger als 8 GiB
  nutzbarem Gesamt-RAM, weniger als 3 GiB freiem RAM oder mindestens 80 Prozent
  CPU-Auslastung wird auf einen Rechenplatz begrenzt. Bereits laufende Arbeit
  wird dadurch nicht abgebrochen.
- Vor dem Start berücksichtigen Aufgaben einen geschätzten Speicherbedarf und
  lassen mindestens 512 MiB beziehungsweise zehn Prozent des Gesamtspeichers
  frei. Reicht der Spielraum für eine zusätzliche Prozesskopie nicht, läuft die
  vorhandene Berechnung im aufrufenden Hintergrundthread. Das ist eine
  Vorsichtsregel, keine harte RAM-Quote.
- Die koordinierte Hintergrundarbeit beginnt mit zwei Slots und erweitert auf
  höchstens vier. Kleine PCs oder Speicher-/CPU-Druck behalten zwei. Bei bis zu
  vier logischen Prozessoren erhält die Suchspur nur einen Slot.
- Untergeordnete Datenabfragen verwenden ein bis drei Verbindungen; die
  Routenprüfung bleibt auf ein bis zwei begrenzt. Dauerhafte Listener und die
  Hilfsthreads des Prozesspools sind keine zusätzlichen Such-Worker.
- Keine CPU-Affinität, keine neue CPU-spezifische Bibliothek und keine Änderung
  der bisherigen Windows-Architektur. Das Betriebssystem verteilt die Prozesse
  auf die verfügbaren Kerne. Die neuen Grenzen berücksichtigen auch die für
  den Prozess verfügbaren logischen Prozessoren.
- Ein ausgefallener Pool kann neu entstehen; vorhandene Hintergrundberechnungen
  dienen als Rückfall. Fachliche Berechnungsfehler werden nicht still erneut
  ausgeführt. Nach 30 Sekunden ohne Arbeit werden eigene Rechenprozesse beendet.

Die Oberfläche zeigt die aktive Rechenkapazität und wartende Aufgaben.
Zeit, CPU-Aufwand und Warte-/Transferzeit werden pro Aufgabenart lokal gezählt.
Die Ressourcenerfassung läuft in Workern; QML liest nur den gespeicherten Stand.
Katalogabgleich alle zehn Minuten, Serverstatistik alle 15 Minuten und die
gebündelte UI-Veröffentlichung alle zwei Sekunden bleiben enthalten.

## Messungen

Drei gleichzeitig angeforderte synthetische Aufgaben: Journal-Projektion mit
60.002 Ereignissen, Powerplay-Zusammenführung mit 100.000 Beobachtungen und die
kurze Commander-Auswertung. Commander bleibt in beiden Varianten im Thread.
Alle Ergebnis-Hashes stimmen in allen Läufen überein.

| Ablauf | Gesamtdauer kalt / warm | Größte UI-Lücke kalt / warm |
|---|---:|---:|
| Hintergrundthreads | 0,460 / 0,333 s | 42,133 / 56,673 ms |
| Gemeinsamer Rechenpool | 0,658 / 0,285 s | 37,059 / 30,864 ms |
| Simulation: zwei logische Prozessoren, 4 GiB RAM, ein Rechenprozess | 0,782 / 0,483 s | 30,167 / 31,704 ms |

Der erste Prozessstart kostet Zeit. Wiederholte Arbeit profitiert hier von der
Aufteilung; das ist keine allgemeine Beschleunigung aller Funktionen. Die kleine
PC-Konfiguration prüft das Verhalten der Grenzen auf dem vorhandenen Rechner;
sie ersetzt keinen Test auf einem echten älteren Prozessor.

Der QML-Test verwendet denselben eingefrorenen öffentlichen Bestand wie zuvor:
391.212 Ringe, 150.000 Warenzeilen und 94.066 Powerplay-Eingangsbeobachtungen.
Alle HTTP-Aufrufe sind in diesen Läufen gesperrt. Beim ALL-500-Mischtest kommen
ein synthetisches Journal mit 20.000 weiteren Ereignissen, ein echter
Journal-Refresh, Powerplay-Aufbereitung und lokale Marktaktualisierung hinzu.

| Suche | Erstes vollständiges Ergebnis | Größte UI-Lücke kalt / warm | Peak Mining-Prozess |
|---|---:|---:|---:|
| Platinum, 250 LY | 6,119 s | 394,612 / 381,011 ms | 506,5 MiB |
| ALL COMMODITIES, 500 LY, Mischlast | 42,798 s | 404,531 / 345,382 ms | 2.382,8 MiB |

In diesen vier Suchphasen gab es keine UI-Lücke über 500 ms und keine
QML-Diagnosefehler. Fünf Seitenwechsel im lokalen Abgleich benötigten etwa
61–220 ms; die größte Ereignislücke dieser Phase betrug 55,526 ms.
Journal und Mining verwendeten denselben Rechenprozess, Powerplay einen zweiten.
Die vorbereitete Powerplay-Veröffentlichung entspricht exakt der bisherigen
Zusammenführung. Die Vergleichsfelder und Reihenfolge aller 100 angezeigten
Routen stimmen kalt und warm mit den vorherigen Berichten überein.

ALL-500-Inhalt: `2e5aede1a369760d8bf26050e8c5a39279dd49c49237ff7ddb3d19f79a461be5`.
ALL-500-Reihenfolge: `2db381afd094624db9265306a2aa5faf06e7483682d95e2116537241de0062cc`.

Die aktuellen Suchzeiten und maximalen UI-Lücken sind höher als in den früheren
Einzelläufen (Platinum 3,818 s; ALL-500 36,898 s). Der ALL-Lauf hat zusätzliche
Mischlast, die Messungen sind kein gleichzeitiges A/B-Experiment. Eine allgemeine
Beschleunigung der Mining-Suche ist damit **nicht belegt**; der Schwerpunkt
dieses Schritts ist die begrenzte, an den PC angepasste Lastverteilung.

## Prüfungen und Testbuild

- **1.334 unittest-Prüfungen bestanden**, einschließlich echter Windows-Prozesse,
  Ergebnisgleichheit des gesamten App-Zustands, Profilwechsel, Speichergrenzen,
  Prioritäten, Wiederherstellung, Abschalten und serieller Netzwerkabfragen.
- Windows-Portable mit Python 3.13.15, PySide6 6.11.2 und PyInstaller 6.22.3 gebaut.
  Der Build enthält die bisherige Versionsressource 1.0.7.
- **35 von 35 Prüfungen der gepackten EXE bestanden**, darunter alle Seiten,
  Dialoge, Mining und die generischen Journal-/Powerplay-Rechenfunktionen.
  Die EXE beendet sich mit Exitcode 0.
- Keine fremden ICU-DLLs im Bundle. Repository-Hygiene und `git diff --check`
  bestanden. Deutsche Vorschau und schmale Ansicht mit fehlenden Daten ohne
  QML-Diagnosefehler gerendert und geprüft.

Artefakte und Rohmessungen liegen unter `.test-tmp/adaptive-work-20261010/`.
Die öffentlich nachvollziehbaren Vergleichsfelder sind im separaten
`mining-resultate-adaptiv.json` zusammengefasst. Der portable ZIP-Testbuild
enthält keine Testprofile oder Commander-Beobachtungen.

## Verbleibender Feinschliff

Der Start hatte auch nach Auslagerung der Bestandszählung noch ungefähr
**2,5 Sekunden** Ereignislücke. Die QML-Erstellung und weitere Startarbeit
bleiben zu untersuchen. Der Mining-Prozess benötigt für ALL-500 weiterhin etwa
2,33 GiB zusätzlich; auch die Datenübertragung zwischen Prozessen kann kurze
UI-Pausen verursachen. Der neue Pool garantiert keine speicherarme oder
vollständig pausenfreie Ausführung.

Als nächster messbarer Schritt bieten sich die verbleibende QML-Startarbeit,
kleinere Übertragungen großer Katalogdaten und gezieltes Profilieren weiterer
schwerer Auswertungen an. Die vorhandenen Tests laufen überwiegend mit
Software-Rendering ohne physische Eingabe; Tests auf weiteren echten PCs und
mit dem normalen Windows-Renderer bleiben sinnvoll.
