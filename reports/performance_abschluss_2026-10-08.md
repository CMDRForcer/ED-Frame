# ED-Frame: Performance-Abschlussbericht

Stand: 8. Oktober 2026. Änderungen am Quellcode; vorhandene Benutzerdaten bleiben erhalten.

## Ergebnis

Die untersuchten regelmäßigen GUI-Pfade warten nicht mehr auf vollständige
Journal-Auswertung, große Katalogimporte oder historische Archivschreibvorgänge.
Das Netzwerk allein im Hintergrund auszuführen hatte bisher nicht gereicht:
nachgelagerte Verarbeitung und einige UI-Abfragen konnten Qt weiterhin blockieren.

Dieser Durchgang ergänzt die bereits im Arbeitsverzeichnis vorhandenen
Performance-Fixes. Es wurden keine bestehenden Profile, Journale, historischen
Beobachtungen, Datenbanken oder Sicherungen gelöscht, komprimiert oder migriert.
Keine Funktionen, Suchfilter, BGS-Prognosen oder Signal-Laufzeiten wurden entfernt
oder fachlich verändert. Keine Server-Änderungen wurden in diesem Durchgang deployt.

## Neue Funde und Fixes dieses Durchgangs

| Fund | Änderung | Absicherung |
| --- | --- | --- |
| CMDR-Karten und Finanzdiagramme konnten den vollständigen Journal-Cache im GUI-Thread abrufen und auf dessen Verarbeitung warten. | Karten, Historie und Zusammenfassungen werden in einem Worker vorbereitet. Alle sieben Diagramm-Zeiträume stehen anschließend im Cache bereit. | Bestehende Berechnungen unverändert; Zustand, Profil und Kredit-Snapshot begrenzen die Gültigkeit. Zwischenstände eines anderen CMDR werden nicht angezeigt. |
| Regelmäßige Standort-/Profilabfragen und EDDN-Profilpfade konnten denselben Journal-Lock beanspruchen. | GUI prüft nur die Änderungssignatur; Auflösung von Profil, Standort und zugehörigen Dateien läuft im Worker. | Verzögerte Ergebnisse werden geprüft; ein unbekannter aktueller Standort bleibt unbekannt. Exobiologie nutzt nicht die alte Systemadresse. |
| Journal-Diagnosen sortierten Dateien und lasen den letzten Datensatz bei UI-Abfragen. | Datei-I/O läuft im Worker; Getter liefern den Cache und berechnen nur dessen Alter neu. | Polling gedrosselt, Anfragen zusammengefasst; Fehler und veraltete Root-/Profil-Ergebnisse getestet. Qt-Timer werden nicht aus dem Worker gelesen. |
| EDDN konnte einen großen Rückstand in einem GUI-Durchlauf vollständig lesen. | Maximal 500 vollständige Datensätze pro Durchlauf, insgesamt über alle Dateien. Der nächste Durchlauf setzt am gesicherten Cursor fort. | Auch ungültige/unsupportete Zeilen zählen zum Budget. Teilzeilen bleiben offen; Queue-Sicherung erfolgt weiterhin vor Cursor-Fortschritt. Kein Upload-Baseline-Abschluss mit ungeprüften Profilpfaden. |
| Live-Signal-Batches mischten und archivierten Beobachtungen im GUI-Thread. | Zusammenführung, Verdrängungsarchivierung, Ablaufprüfung und Überlaufarchivierung laufen im Worker. GUI veröffentlicht ein vorbereitetes Ergebnis. | Neue Eingänge werden zusammengefasst; gleichzeitige Server-Updates führen zu einem Rebase. Archivfehler behalten Daten für Wiederholung bzw. aktive Speicherung. |
| Manuelle State-Finds-Aktualisierung konnte Fertigstellung melden, obwohl der neue Worker noch lief. | Status bleibt währenddessen „REFRESHING“; Zähler werden nach Abschluss veröffentlicht. | Mehrere zusammengefasste Teil-Batches werden aufsummiert. |
| Profilwechsel konnte eine noch nicht veröffentlichte oder zur Wiederholung zurückgehaltene Beobachtung verlassen. | Übergabe wird bis zur Verarbeitung ursprünglicher HGE-/Mining-Eingänge zurückgestellt; keine Warteoperation im GUI-Thread. | Bisherige Pfade und Profile bleiben gebunden. Finales Beenden übernimmt unveröffentlichte Eingänge; späte Ergebnisse überschreiben sie nicht. |

Wichtige Dateien: `controller_commander.py`, `commander_projection.py`,
`controller_journal_health.py`, `controller_eddn.py`, `controller_exobiology.py`,
`state_core.py`, `controller_navigation.py`, `hge_batch.py` und `controller.py`.

## Bereits enthaltene Performance-Arbeiten

Die vorangegangenen Durchgänge haben die anderen Hauptursachen adressiert:

- SQLite/WAL-Lesezugriffe unabhängig vom Writer-Lock großer Katalogimporte;
  JSON-Schreibsperren pro Zieldatei statt einer globalen Sperre.
- Katalog-Abschlussverarbeitung, Quellenstatus, Such-Vormerkung, lokale Marktimporte,
  Verifikationsspeicherung und State-Finds-Seitenspeicherung außerhalb von Qt.
- Domain-spezifische Caches, weniger unnötige Fleet-/Mining-Neuberechnungen;
  verzögertes Speichern der Tab-Auswahl und asynchrones Erzeugen von Seiten.
- Streaming großer Katalogdateien, gemeinsame wiederholte Strings und unveränderte
  Quellzeilen statt großer dekorierter Kopien.
- Mining-Ergebnisse bleiben bei derselben Suche während Hintergrundaktualisierungen
  sichtbar; stabile Zeilen erhalten Auswahl und Scrollposition.
- Parallele unabhängige Netzwerkabfragen, wiederverwendete HTTP-Verbindungen und
  Vorrang expliziter Suchen vor Hintergrund-Warming.
- Verlustfreie Komprimierung ausschließlich neuer Historien-Payloads und neuer
  Sicherungen mit Legacy-Lesepfad. Alte Gigabyte-Dateien bleiben ausdrücklich bestehen.

Details stehen in den übrigen Performance-Berichten im Ordner `reports/`.

## Kontrollierte Messung

Reproduzierbar mit `.venv/Scripts/python.exe tools/benchmark_remaining_ui.py`.
Synthetischer Journal-Datensatz mit 120.001 einfachen Ereignissen; keine echten
Profile oder Netzwerkzugriffe. Die Zeiten hängen von Rechner und Last ab.

| Prüfung | Gemessen |
| --- | ---: |
| Frühere Karten-/Historien-Neuberechnung für sieben Zeiträume | 85,882 ms |
| Neue Vorbereitung aller Zeiträume, einmal im Worker | 16,153 ms |
| Cache-Abfragen für Karten plus sämtliche Zeiträume/Zusammenfassungen, Mittel von 1.000 Durchläufen | 0,018 ms je Durchlauf |
| Start der vier Worker für CMDR, Standort, Diagnose und Live-Signale | 1,022 ms |
| Tatsächliche Qt-Heartbeats bei 250 ms künstlich blockierter Hintergrund-I/O | 25 |
| Größter Abstand zwischen diesen 10-ms-Heartbeats | 12,862 ms |

Damit ist belegt, dass diese GUI-Einstiegspunkte nicht auf die künstlich gesperrten
Datenzugriffe warten. Es ist **kein** Live-Benchmark des installierten Programms,
keine Messung aller realen Journale und keine pauschale Framerate-/RAM-Garantie.

## Prüfung

- Erster vollständiger Lauf: **1.096 App-Tests bestanden in 101,888 Sekunden**,
  einschließlich Offscreen-QML-Seiten und Dialogen.
- Anschließend Profilübergabe zusätzlich abgesichert: **27 neue gezielte Tests**,
  alle bestanden; bestehende **9 Profil-Tests** ebenfalls bestanden.
- EDDN-Verifikation nach der finalen Baseline-Sicherung: **27 Tests bestanden**.
- **97 Server-Tests bestanden**. Der produktive Server wurde dabei nicht verändert.
- Finaler vollständiger Lauf nach allen Sicherungen: **1.097 App-Tests bestanden
  in 102,248 Sekunden**, einschließlich der QML-Prüfungen.
- `git diff --check`, Repository-Hygiene sowie Geheimnis-/Profilpfad-Prüfung der
  neuen Dateien bestanden.

Fehler-/Korruptionsmeldungen in den Testausgaben stammen aus absichtlich injizierten
Fehlern in Wegwerf-Testdaten, nicht aus einem beschädigten Benutzerprofil.

## Grenzen und noch nötige Produktprüfung

Die zuletzt gezeigte installierte Version ist **1.5.39**. Die Änderungen sind im
Arbeitsverzeichnis und ersetzen diese EXE nicht automatisch. Es wurde weder ein
Release veröffentlicht noch die Installation überschrieben; die Vorgabe war,
den Code zu verbessern und vorhandene Dateien zu behalten.

Vor Nutzung im installierten Programm sind daher Build/Installation und ein
Live-Test mit dem echten Profil sinnvoll: Tabwechsel während Server-Sync,
Mining-Erstsuche und Folgesuche, CMDR/Fleet, Diagramm-Zeitraumwechsel und Profilwechsel.
Ohne laufende App wird keine erfundene reale Beschleunigungs- oder RAM-Zahl behauptet.

Der bestehende lokale Datenordner wird durch diese Arbeit nicht kleiner. Seine
zuvor ermittelte Größenordnung von rund 4,7 GiB entfällt hauptsächlich auf Markt-DB,
Legacy-Sicherung, Historie und Ring-Katalog. Das ist gespeicherte Datenmenge, nicht
automatisch dauerhaft belegter RAM. Eine spätere Bestandsmigration benötigt eine
separate Entscheidung; sie wurde ausdrücklich nicht vorgenommen.

Seltene explizite Aktionen wie Engineering-Plan-Import/Export und tatsächliches
Umschalten großer Profile besitzen noch lokale Lese-/Schreibschritte. Sie sind
nicht Bestandteil einer behaupteten vollständig I/O-freien Oberfläche. Netzwerklatenz
und Python-CPU-Arbeit bleiben reale Grenzen; Worker sind kein pauschales Heilmittel.

## Abschluss

Quellcode und Bericht werden vor dem gewünschten Herunterfahren gespeichert.
Windows wird regulär mit `shutdown.exe /s /t 0` heruntergefahren, **ohne** erzwungenes
Schließen (`/f`). Ungespeicherte Arbeit anderer Programme kann Windows dadurch
weiterhin schützen. Die Annahme des Befehls lässt sich bestätigen, das endgültige
Ausschalten des eigenen Rechners danach nicht mehr unabhängig beobachten.
