# ED-Frame: Start und Bedienbarkeit – 10.10.2026

Lokaler Teststand auf Basis von **1.0.8 / 6334c48**. Kein Commit, Push,
Release oder Server-Rollout.

QML wird jetzt asynchron geladen. Die Fenster entstehen auf dem UI-Thread
in kurzen Abschnitten mit einem Qt-Zeitbudget von 3 ms; dazwischen kann Qt
weitere Ereignisse bearbeiten. Der zugehörige Timer stoppt im Leerlauf.
Das Hauptfenster erscheint nach abgeschlossener Einrichtung. Aktivierungen,
Anmeldungsrückmeldungen während des Ladens und beide Overlays funktionieren
weiter. Es werden die vorhandenen Qt-Bibliotheken verwendet.

## Messung

Direkter Vergleich mit dem unveränderten Ausgangscode auf diesem PC,
ohne Profiler, offline und mit Qt-Offscreen-/Software-Rendering.
Die Pause bezeichnet den größten Abstand eines 10-ms-UI-Timers.

| Journal | Größte Pause vorher → jetzt | Erstes Fenster vorher → jetzt |
|---|---|---|
| Kleines synthetisches Journal | 1.338 → 119 ms | 1,36 → 1,37 s |
| 30.000 zusätzliche Ereignisse | 1.374 → 134 ms | 1,39 → 1,43 s |

Die größte Startpause sinkt um rund **90 %**. Die gesamte Startdauer bleibt
ungefähr gleich.

Mit 185.818 Ringen, 30.193 Marktzeilen und 3.743 Powerplay-Beobachtungen:
ALL-COMMODITIES-Suche bei 500 LY, zusätzliches Journal mit 20.000 Ereignissen,
Journal-Refresh und parallele Powerplay-Aufbereitung. Größte UI-Pause während
der Suchlast: **53 ms**; Seitenwechsel etwa **30–126 ms**. Keine QML-Fehler.
Ein weiterer Lauf liefert 100 verifizierte Routen; kalte und wiederholte Suche
haben identische Ergebnisse und Reihenfolge. Unterschiedliche Filter der
beiden Läufe dienen unterschiedlichen Belastungsfällen.

## Prüfung und Test morgen

**1.373 App-Tests bestanden.** Die portable EXE besteht zusätzlich **35
Smoke-Prüfungen**, einschließlich echter separater Mining-, Journal- und
Powerplay-Rechenprozesse. Ladefehler, Abbruch, Anmeldung während des Starts
und Overlay-Sichtbarkeit sind geprüft. Python-Kompilierung, Repository-Hygiene
und Diff-Prüfung bestehen.

Testversion: `output/ED-Frame-Starttest-20261010-Windows/ED-Frame/ED-Frame.exe`.
Die bisherige App vollständig beenden, auch im Tray, dann diese EXE starten.
Start, Seitenwechsel, Overlays und Bedienbarkeit während einer breiten Suche
mit deinen normalen Daten prüfen. Das vorhandene Commander-Profil wird benutzt.

Die verbleibende Controller-Einrichtung braucht hier vor dem Qt-Ereignisloop
noch etwa 0,1–0,15 s. Die Messungen ersetzen keinen Test auf anderen PCs oder
mit dem normalen Grafik-Renderer. Rohmessungen, Test- und Build-Protokolle
liegen im lokalen Aufgabenordner unter `outputs/startup-quality-20261010`.
