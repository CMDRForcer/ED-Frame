# Portabler Updater — lokaler Stand 13.10.2026

Dieser Bericht dokumentiert den lokalen Teststand vor der freigegebenen Veröffentlichung als 1.0.11. Aktuelle Installationshinweise stehen in docs/releases/1.0.11.md.

Implementiert:
- Ein täglicher UTC-Release-Check beim Start/über einen 30-Minuten-Timer,
  verzögert und über die vorhandene begrenzte Hintergrundwarteschlange.
  Manuelle Prüfung unter Settings → About. Dev-/Smoke-Builds prüfen nicht
  automatisch; EDFRAME_NO_UPDATES=1 unterbindet auch manuelle Checks.
- Dezenter Sidebar-Hinweis, in kompakter Sidebar als Piktogramm, mit Versions-
  hinweisen und Später. Global gespeicherte Prüfeinstellung und optionaler
  automatischer Download; Installation erfolgt erst nach bewusster Bestätigung.
- Ausschließlich vollständige reguläre Releases des eigenen GitHub-Repositories.
  Numerischer Vergleich mit besonderer Behandlung der alten 1.5.0–1.5.43-Linie.
  Keine Commander-Daten oder Installations-IDs an GitHub.
- Begrenzter, abbrechbarer Download mit Fortschritt höchstens viermal/Sekunde.
  Nur erlaubte HTTPS-Downloadhosts, begrenzte Umleitungen, Größen, Zeitlimits,
  ZIP-Einträge, Paketversion und SHA-256. Ausführbare Pakete enthalten eine
  vollständige gehashte Dateiliste; Pfad-Traversal, doppelte Windows-Namen,
  Symlinks und eingeschlossene bekannte Profildateien werden abgewiesen.
- Installer bereitet den Kandidaten neben dem Programmordner auf dessen
  Datenträger vor und verwendet einen separat kopierten Runtime-Helfer. Der
  Helfer wartet per Windows-Prozesshandle auf das tatsächliche Prozessende.
  Die bestehende Single-Instance-Sperre verhindert einen zweiten normalen
  App-Start während Sicherung/Austausch.
- Vollständige Kopie von ED-Frame-Nutzerdaten und vorhandenem Legacy-Datenordner
  nach dem Prozessende, vor Austausch/erstem Start. Alle Profile, Pläne,
  Zugangsdaten, lokale Kataloge und Installations-ID werden mitgesichert.
  App-Dateien und Datenordner dürfen nicht überlappen.
- Wiederherstellung bei Austausch-/Startfehlern. Der erste Start bestätigt die
  genaue Transaktion mit Token, Version und PID. Fehlgeschlagene neue App-
  und Profildaten werden ebenfalls behalten. Vorige App bleibt in einem
  separaten Schwesterordner; Profilsicherungen sind in About erreichbar.
- Release-Workflow erzeugt/prüft den Paketmanifest und führt künftig auch die
  echten Windows-Update-/Rückfallprüfungen vor Veröffentlichung durch.

Geänderte Dateien:
- ed_companion/updates/{client,package,install,helper}.py und __init__.py
- ed_companion/phase14/controller_updates.py und controller.py
- phase14_main.py: früher Helper-Einstieg, Startbestätigung, beendeter Update-Start
- qml/components/{UpdatePanel,UpdateNotice}.qml und Main.qml
- ed_data/i18n/{en,de,es,fr}.json: vollständige Update-Texte
- ED-Frame.spec und .github/workflows/release.yml: Manifest und Paket-Prüfungen
- .gitignore und tests/check_repository_hygiene.py: lokale Updatezustände ausschließen
- README.md und PORTABLE_README.txt: Ablauf, Datenhaltung, Bootstrap
- tests/{test_updates,test_updates_qml,verify_update_package}.py

Testergebnisse:
- Gesamtlauf: 1.451 Tests bestanden, 397,3 Sekunden.
- Nach den abschließenden Anpassungen: 131 relevante Regressionstests bestanden;
  anschließend nochmals 32 Update-/i18n-/Layout-Tests, einschließlich schmalem
  1120×700-Fenster, sechs Themes, vier Sprachen und 100/115/150 % Skalierung.
- Zwei isolierte Windows-Szenarien mit echter Dateisperre, tatsächlichem
  Prozessende, portabler EXE, Neustart und Wiederherstellung bestanden.
  Jeweils zwei Profile, Pläne, Credential-Dateien und Installations-ID erhalten;
  danach jeweils 33 App-Smoke-Punkte PASS.
- Letztes Paket: 35 App-Smoke-Punkte PASS, einschließlich getrennter
  Mining-/Compute-Prozesse. Keine fremden ICU-DLLs.
- ZIP-Einträge und alle 3.625 Dateihashes gegen Paketmanifest geprüft.
- Geänderte/neue Dateien auf Profile/Zugangsdaten/Privatpfade geprüft;
  Kompilierung und git diff --check ohne Fehler.

Lokaler Test:
1. Alte App einschließlich Tray beenden.
2. ED-Frame-Updater-Local-Test-Windows.zip vollständig in einen neuen
   beschreibbaren Programmordner entpacken; _internal muss neben der EXE bleiben.
3. Settings → About öffnen, prüfen/deaktivieren, Hinweise und Layout ansehen.
   Vorhandene Pläne, Profile und Einstellungen werden aus dem gleichen
   LOCALAPPDATA-Datenbestand weiterverwendet.
4. Gegen den realen GitHub-Stand wird derzeit keine neuere Version angezeigt:
   Der lokale Build verwendet noch APP_VERSION 1.0.10. Update/Rückfall wurden
   mit isolierten Paket-/Profilfixtures geprüft, nicht mit persönlichen Daten.

Grenzen:
- Der veröffentlichte Release 1.0.10 hat noch keinen Updater. Die erste
  veröffentlichte Version mit Updater einmal manuell installieren; danach
  funktionieren kompatible Folgeversionen innerhalb der App.
- Nur Windows-Pakete können sich selbst installieren. Quellcode-Stände werden
  nicht überschrieben; ein beschreibbarer separater Programmordner ist nötig.
- Backups und vorherige Programmversionen benötigen zusätzlichen Platz und
  werden für die Wiederherstellung behalten, nicht automatisch gelöscht.
- Der Watchdog prüft den ersten erfolgreichen GUI-Start, nicht sämtliche
  späteren Spielfunktionen. Bei abruptem Stromausfall bleiben vorherige Dateien
  und Transaktionsaufzeichnung für Wiederherstellung erhalten; es gibt noch
  keinen separaten GUI-Recovery-Assistenten für einen unterbrochenen Helfer.
- Hashprüfung und HTTPS binden das Paket an den eigenen GitHub-Release; dieser
  Stand fügt noch keine zusätzliche Code-/Manifest-Signatur mit eigenem Schlüssel hinzu.

Kein Commit/Push/Tag/Release, kein GitHub-Workflow gestartet und kein Server-Deploy.
Installierte App und persönliche Profile wurden nicht verändert.
Der neue Workflow ist ausschließlich lokal vorbereitet.
