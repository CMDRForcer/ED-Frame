# UI und Hintergrundarbeit – lokaler Entwicklungsstand, 10.10.2026

Historischer Zwischenstand vor dem Rollout. Veröffentlichung und Prüfung mit
gefülltem Marktbestand: [Bericht für 1.0.8](mining_merit_rollout_2026-10-10.md).

Die Serverübersicht zeigt zusätzliche belegte Daten. Katalogabgleich und
Statusprüfung haben getrennte Zeitpläne, Hintergrundimporte laufen begrenzt,
und die Mining-Berechnung läuft in einem eigenen Windows-Prozess.
Basis: Commit `5dea25fbb3ea7bfc679b3043d7099c036bf68a82`, App-Version 1.0.7.
Die Änderungen sind lokal, uncommitted und unveröffentlicht. Server, Website,
installierte App und echtes Commander-Profil wurden nicht verändert.

## Serverübersicht

- Die Karte „REPORTED ACTIVE SIGNALS“ wurde entfernt. Signalbeobachtungen und
  ihre Lebensdauerprüfung bleiben im Datenmodell erhalten.
- „AKTUALITÄT DER MARKTDATEN“ zeigt den Anteil der gespeicherten Warenzeilen
  mit Beobachtung innerhalb der letzten 24 Stunden und die Zahl älterer Zeilen.
- „AKTIVITÄT DER DATENQUELLEN“ zeigt projizierte Datenzeilen sowie genutzte und
  ignorierte EDDN-Nachrichten in 24 Stunden. Das sind Verarbeitungszahlen,
  keine zusätzlichen eindeutigen Systeme oder Stationen.
- Zeitstempel der Statistik und letzter erfolgreicher Servercheck sind getrennt.
- Details zeigen zusätzlich bekannte Markt-/Mining-Koordinaten sowie lokale
  Warenzeilen und Stationsinventare.
- Laufende/wartende Aufgaben, Katalogabfragen der letzten 60 Sekunden und
  nächster Abgleich machen die Hintergrundarbeit sichtbar.
- Fehlende Werte erscheinen als „—“. Vollständigkeit beschreibt gespeicherte
  Datensätze; sie behauptet weder Galaxieabdeckung noch frische Beobachtungen.

Die Anzeige verwendet bestehende Statusfelder der Server-API. Hierfür ist kein
Server-Deployment erforderlich. Die Vorschau-PNG verwendet ausdrücklich
gekennzeichnete Beispieldaten und ist keine neue Live-Servermessung.

## Ablauf und Priorisierung

| Arbeit | Neuer Ablauf |
|---|---|
| Automatischer Katalogabgleich | Ein Start pro 10 Minuten; wiederholte Statuschecks starten keinen weiteren Zyklus |
| Automatische Serverstatistik | Alle 15 Minuten; manueller Check hat Suchpriorität |
| Markt-Vorwärmung | Frühestens nach 5 Minuten; nur bei geöffnetem Mining Finder und ohne aktive Routenberechnung |
| Hintergrundimporte | Höchstens ein Worker; neue Importe warten während interaktiver Arbeit |
| Interaktive Abfragen | Eigene Kapazität mit höchstens zwei Workern |
| Journal/Commander | Eigene Worker-Kapazität unabhängig vom Katalogimport |
| UI-Veröffentlichung | Marktrevision und Aktivitätsanzeige gebündelt alle 2 Sekunden |
| Live-EDDN | Projektion im Listener; Übergabe in 2-Sekunden-Paketen statt eines Qt-Events pro Nachricht |
| Mining | Ein wiederverwendeter Unterprozess; Qt übernimmt das fertige Ergebnis |

Ein Abgleich liest weiterhin alle erforderlichen Delta-Seiten und speichert
Fortsetzungscursor. Ein Erstabgleich oder Rückstand kann deshalb länger laufen
und mehrere Anfragen verursachen. Die Intervalle beziehen sich auf den Start
eines Abgleichs, nicht auf einen einzelnen HTTP-Aufruf. Aktive Hintergrundarbeit
wird nicht gewaltsam unterbrochen; angeforderte Suchen haben eigene Kapazität.

Ein Statussignal setzt die Mining-Ergebnisliste nicht mehr unnötig zurück.
Die eigentliche Datenrevision bleibt sofort gültig; nur die Veröffentlichung an
die Oberfläche wird gebündelt. Die Prüfung einer Suche wartet bei neuen
Marktdaten auf den passenden fertigen Plan.

Der Mining-Prozess erhält den Ring-Revisionsdeskriptor und liest die lokalen
Marktdaten. Er schreibt keine Marktdatenbank und führt keine Reparatur aus.
Profil-, Reset- und Ergebnisrevisionen bleiben geprüft. Beim Beenden wird nur
der eigene lesende Rechenprozess gestoppt. Ausstehende Beobachtungen werden
abschließend übernommen, einschließlich des neuesten Powerplay-Snapshots.

## Messung mit gefülltem Marktbestand

Gleicher eingefrorener Datenbestand und Beobachtungszeitpunkt wie beim Vergleich
vom 09.10.: 391.212 Ringe, 150.000 Warenzeilen, 94.066 Powerplay-Beobachtungen.
Native QML-Oberfläche, Software-Renderer, 100 angeforderte Ergebnisse.
Die Läufe verwenden lokale Provider und messen keine aktuelle Serverlatenz.

| Suche | Erstes vollständiges Ergebnis | Größte UI-Lücke kalt / warm | Peak UI-Prozess | Peak Rechenprozess |
|---|---:|---:|---:|---:|
| Platinum, 250 LY | 3,818 s | 176,807 / 165,298 ms | 358,9 MiB | 506,3 MiB |
| Platinum, 500 LY | 5,543 s | 192,442 / 175,525 ms | 362,9 MiB | 601,7 MiB |
| ALL COMMODITIES, 250 LY | 20,664 s | 178,117 / 159,405 ms | 348,7 MiB | 1.321,1 MiB |
| ALL COMMODITIES, 500 LY | 36,898 s | 185,864 / 167,526 ms | 358,3 MiB | 2.385,9 MiB |

Während dieser acht Suchphasen gab es keine UI-Lücke über 500 ms. Die vorherige
ALL-500-Messung hatte bis zu 1.709 ms. Das sind vergleichbare Läufe an zwei Tagen,
kein zeitgleiches A/B-Experiment. Die 10-ms-Messsonde ist von der neuen
100-ms-Diagnose der App zu unterscheiden.

Für alle vier Varianten stimmen kalt und warm die finalen Vergleichsfelder
und Reihenfolge mit den bisherigen Berichten überein. Die Hashes der vollständigen
veröffentlichten Listen stimmen ebenfalls; bei unveränderter warmer Liste gilt
deren zuvor veröffentlichter Hash. Ein sofort sichtbares warmes Cache-Ergebnis
ist nicht mit einer abgeschlossenen neuen Berechnung gleichzusetzen.

ALL-500-Inhalt: `2e5aede1a369760d8bf26050e8c5a39279dd49c49237ff7ddb3d19f79a461be5`.
ALL-500-Reihenfolge: `2db381afd094624db9265306a2aa5faf06e7483682d95e2116537241de0062cc`.
39 Ergebnisse haben bestätigte Powerplay-Fakten, 61 weiterhin fehlende Fakten.
Es werden keine fehlenden Informationen als bestätigt ausgewiesen.

Die Prozessaufteilung senkt die Belastung des UI-Prozesses. Sie belegt keine
Senkung des gesamten RAM-Verbrauchs: Der Rechenprozess benötigt bei ALL-500
weiterhin rund 2,33 GiB zusätzlich zum UI-Prozess. Auch der App-Start hatte im
Test noch eine etwa 2,1 Sekunden lange Ereignislücke. Diese beiden Punkte bleiben
die nächsten Optimierungsziele; eine Zusicherung vollkommen pausenfreier
Bedienung lässt sich aus den Tests nicht ableiten.

## Prüfung und lokaler Build

- Vollständige Testsuite: **1.319 Tests, PASS**, 138,528 Sekunden.
- Zusätzliche QML-/Worker-Prüfung nach den letzten QA-Erweiterungen:
  **15 Tests, PASS**, 120,269 Sekunden.
- Native Suchmatrix: **4 Varianten × kalt/warm, PASS**, keine QML-Laufzeitfehler.
- Vollständiger App-Smoke-Test aus dem Quellcode: **33 Bereiche, PASS**.
- Windows-EXE: **33 Bereiche plus explizite Mining-Prozess-Prüfung, PASS**, Exit 0.
  Der echte eingefrorene Unterprozess meldet eine andere PID; kein zweites
  App-Fenster oder konkurrierender Single-Instance-Start.
- Vorschau mit englischen/deutschen und unbekannten Werten ohne QML-Fehler;
  Karten füllen die Zeilenhöhe auch bei umbrochenen deutschen Texten.
- `git diff --check`: PASS.

PyInstaller 6.22.3, Python 3.13, PySide6 6.11.2. Der Build-PATH muss auf die
virtuelle Umgebung, Python-Basis/DLLs und Windows/System32 begrenzt sein. Der
Werkzeug-PATH enthält eine fremde Poppler-ICU-DLL, deren unverträgliche Exporte
den Qt-Start verhindern. Der bereinigte Build enthält weder `icuuc.dll` noch
`icudt78.dll`; der Release-Workflow prüft diese Bedingung bereits.

Der lokale Windows-Build behält die Ressourcen-Version **1.0.7** und ist ein
unveröffentlichter Entwicklungsstand. Der gesamte portable Ordner wird benötigt,
einschließlich `_internal`. Tests verwenden isolierte synthetische Profile.

Rohberichte, Logs und Screenshots liegen unter
`.test-tmp/ui-decoupling-20261010/`. Die vier endgültigen Suchberichte heißen
`final-platinum-250`, `final-platinum-500`, `final-all-250`, `final-all-500`.
