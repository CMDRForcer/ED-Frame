# UI-Qualität · 11.10.2026

Punkt 5 des Fahrplans lokal umgesetzt. Grundlage ist ED-Frame 1.0.8 einschließlich der lokalen Startoptimierung vom 10.10.2026.

- **Diagnose:** Alle Informationsblöcke bleiben durch Scrollen erreichbar. Statistik und Protokollkarten passen sich der Fensterbreite an. Deutsche Beschriftungen ergänzt, den sichtbaren `%1`-Platzhalter beim Renderer entfernt und lange Dateinamen per Tooltip zugänglich gemacht.
- **Mining:** Aktualisieren, Kopieren und Suche bearbeiten berücksichtigen die Textbreite. Die Statuszeile bleibt innerhalb des Fensters; die Auswahlspalte berücksichtigt Übersetzungen. „Warum diese Route?“ ist scrollbar, Quellenangaben überlappen keine anderen Bereiche mehr. Lange Erklärungen haben Tooltips; RES-Beschriftungen sind übersetzt.
- **Warensuche:** Filter sichtbar beschriftet; „Alle“ und die üblichen Warenkategorien übersetzt. Hinweise erklären fehlenden Katalog, erfolglose Namensfilter und leere Angebote. Preise heißen ausdrücklich CR/T; Entfernungen und Datenalter verwenden regionale Zahlenformate. Kategorien und Suchparameter behalten ihre ursprünglichen technischen Werte.
- **Stationsdienste und Buttons:** Hinweise und leere Ansichten umbrechen zuverlässig. Abgekürzte Buttontexte bleiben über Tooltips lesbar. Eine wiederholte Qt-Layoutberechnung beim Öffnen der Warensuche wurde beseitigt.

## Prüfung

18 Hauptseiten und fünf Unteransichten bei 1920 × 1080 sowie 1120 × 700 und UI-Skalierung 1,15 geprüft. Dazu gefüllte Mining- und Warenansichten auf Deutsch, Englisch und Französisch, darunter 1366 × 768. Insgesamt 54 Screenshots ohne unerwartete Textabschneidung; bewusst gekürzte Angaben verwenden Elision bzw. Tooltips.

Alle **1.374 Tests** bestehen auf dem endgültigen Stand. Die gezielten Qt-Tests prüfen Scroll-Erreichbarkeit, lange Texte, leere Ansichten, seltene Waren und unveränderte Suchparameter. Die lokale portable EXE besteht zusätzlich **35 Funktionsprüfungen** einschließlich der separaten Hintergrundprozesse für Mining, Journal und Powerplay. Quellstand und gebündelte QML-/Sprachdateien wurden bytegenau verglichen; Repository- und Datenschutzprüfungen bestehen ebenfalls.

Automatisierte Prüfungen erfolgten offline mit separaten Testprofilen und Beispieldaten. Der Test im laufenden Spiel und auf weiteren Rechnern bleibt Fahrplan-Punkt 6.

## Lokal testen

Testversion: `output/ED-Frame-UI-Test-20261011-Windows/ED-Frame/ED-Frame.exe`.

Die bisherige App vollständig beenden, auch im Tray, dann diese EXE starten. Besonders Diagnose-Scrollen, Mining-Kopierbuttons und Quellenhinweise sowie Warensuche mit langen Namen und leeren Ansichten ausprobieren. Der gesamte portable Ordner muss zusammenbleiben.

Änderungen und Testversion bleiben lokal; keine Veröffentlichung und keine Änderung am Server.
