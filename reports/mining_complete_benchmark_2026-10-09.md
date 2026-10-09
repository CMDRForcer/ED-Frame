# Mining-Suche mit gefülltem Marktstore — lokaler Kandidat 1.0.7

Stand: 2026-10-09. App 1.0.7 / Servercode 0.9.2 sind lokal vorbereitet.
Kein Commit/Push, Release-Tag, GitHub-Release oder Produktiv-Rollout wurde ausgeführt.
Produktiv bestätigt `/healthz` weiterhin einen gesunden Katalogserver 0.9.1.

## 1. Vollständige Messreihe

Eingefrorene öffentliche Kopien: **391.212 Ring-Einträge, 150.000 aktuelle
Marktzeilen** sowie der vorhandene Powerplay-Katalog und Beobachtungen. Die
ursprünglichen Profil-Dateien wurden nur gelesen; Controller und sämtliche
Schreibzugriffe liefen ausschließlich mit synthetischer FID und isolierten
Testkopien. Die konsistente Markt-SQLite-Kopie enthält auch ihre bisherige
öffentliche Historie. Diese wurde weder gelöscht noch in die Archive gepackt.

Origin Shanteneri `[110.9375, -113.0625, 41.21875]`, LASER, REINFORCE für
Aisling Duval, POWERPLAY MERITS, alle Reserven, nur Ringe, L/LARGE-Pad,
Nachfrage 5.000–500.000 T, Marktalter 1 h, 100 Ergebnisse, keine zusätzlichen
Hotspot-/Sekundär-/Systemstatus-Anforderungen. Die Uhr ist für CPU und QML
auf **2026-10-09T18:21:19.145887+00:00** eingefroren; Quellzeiten werden nicht erneuert.

### Domain-Worker inklusive Marktlesen, Rangfolge und Diagnose

Je Fall ein neuer Prozess, drei aufeinanderfolgende Berechnungen. „Erster Lauf“
bezeichnet kalte App-Caches im Prozess, keinen geleerten Windows-Dateicache.
Die Wiederholungen erzwingen die Kandidatenberechnung erneut und lesen die
Märkte neu; regionale Ring- und reine Powerplay-Faktenindizes bleiben warm.
HTTP ist in diesen Vergleichsläufen gesperrt.

| Suche | Vorher erster Lauf | Nachher erster Lauf | Vorher warm, Mittel | Nachher warm, Mittel |
|---|---:|---:|---:|---:|
| Platinum, 250 LY | 4.76 s | 4.97 s | 0.80 s | 0.81 s |
| Platinum, 500 LY | 8.06 s | 7.90 s | 1.88 s | 1.87 s |
| ALL COMMODITIES, 250 LY | 33.18 s | 18.68 s | 28.69 s | 16.86 s |
| ALL COMMODITIES, 500 LY | 75.03 s | 42.24 s | 66.09 s | 31.57 s |

ALL COMMODITIES spart etwa 41 % im warmen 250-LY-Lauf und 52 % bei 500 LY.
Platinum ist innerhalb der Streuung unverändert; hierfür wird keine
Geschwindigkeitsverbesserung behauptet. Im 500-LY-Ausgangslauf entfielen
41 s auf Kandidaten, 10,6 s auf das erste Marktlesen, 13,3 s auf Rangfolge
und 6 s auf das erneute Marktlesen für Diagnose. cProfile bestätigt
7,7 Millionen Kompatibilitätsberechnungen; Profiling-Zeiten selbst gehen
nicht in die oben genannten Laufzeiten ein.

### Native Qt/QML-Suche mit gefülltem Bestand

Die tatsächliche Seite führt Suche, Worker, SQLite-Abfragen, Veröffentlichung
und ihren begrenzten Prüfpass aus. Für reproduzierbare Messungen liefern lokale
Testprovider ausschließlich bereits gespeicherte Originalbeobachtungen; sie
liefern keine neuen Powerplay-Fakten. Dies ist **kein Live-Verfügbarkeitsnachweis**.
Offscreen/Software misst die Qt-Ereignisschleife, nicht D3D oder Eingabe-zu-Pixel.

| Suche | Erste Liste | Prüfpass beendet | Wiederholter Prüfpass beendet | Peak RSS | Größte UI-Lücke während Suche |
|---|---:|---:|---:|---:|---:|
| Platinum, 250 LY | 6.45 s | 12.18 s | 2.08 s | 478 MiB | 386 ms |
| Platinum, 500 LY | 12.86 s | 19.52 s | 5.38 s | 591 MiB | 506 ms |
| ALL COMMODITIES, 250 LY | 35.08 s | 35.14 s | 18.33 s | 1422 MiB | 1083 ms |
| ALL COMMODITIES, 500 LY | 53.49 s | 53.56 s | 31.65 s | 2486 MiB | 1709 ms |

Die erneute Liste ist in 4–81 ms sichtbar, weil bestehende Ergebnisse bewusst
wiederverwendet werden; das ist **keine abgeschlossene neue Berechnung**.
Alle Runs liefern 100 Zeilen, enden ohne QML-Fehler und bestätigen den
Prüfaufruf der jeweiligen Suchrevision. Platinum prüft jeweils sechs Ziele
pro Durchlauf. Bei ALL COMMODITIES sind die ersten sechs Routen bereits aktuell,
sodass der gezielte Prüfpass null neue Jobs benötigt. Unbekannte Fakten in
anderen Zeilen bleiben unbekannt; „Prüfpass beendet“ heißt nicht 100 bestätigte
Routen. Die Wartezeit bis „settled“ enthält zusätzlich drei Sekunden Ruhe.

Die ergänzte Koordinatenübergabe stellt in beiden breiten QML-Suchen **39
passende Markt-/Powerplay-Routen** wieder her, ohne neue Beobachtungen zu
behaupten. Echte Marktlesemengen: 72.685 bei 250 LY, 125.575 bei 500 LY.
Die erste diagnostische QML-Serie vor dieser Fehlerkorrektur las für freie
Startsysteme einen unvollständigen Marktbestand; deren schnellere ALL-Werte
werden nicht als fertige Vergleichswerte verwendet.

Der erste isolierte Start ohne Recovery-Datei erzeugte ein 571-MB-Marktbackup
und benötigte 49,4 s bis zur Bereitschaft. Die fertige QML-Matrix verwendet
dieses bereits in der Testkopie erzeugte Recovery-Backup; Primärdaten und
Evidenzzeiten bleiben unverändert. Ihre Startbereitschaft liegt bei
18.3–31.4 s und ist getrennt von den Suchzeiten ausgewiesen.

**Verbleibende Grenze:** Die breite 500-LY-Suche ist trotz schnellerer
Regelaufbereitung weiterhin teuer: erste QML-Liste nach rund 53 s, ca.
2,43 GiB Peak RSS, Wiederholungsberechnung etwa 32 s. Gen-2-GC-Scans
verursachen UI-Pausen bis 1,71 s. Die nächsten Ansatzpunkte sind weniger
kurzlebige Kandidaten-/Marktobjekte, GC-Aufwand und Rangfolge. Keine Daten
wurden abgeschnitten, Altersfilter erweitert oder unbekannte Fakten bestätigt,
um diese Messwerte zu verbessern.

### Separate öffentliche Live-GET-Abfragen

Nur öffentliche Katalogdaten, kein Controller/Profil, keine Uploads. Beispiel
Platinum bei beiden Radien, keine pauschale ALL-COMMODITIES-Marktanfrage:
Die App wärmt dafür konkrete Waren und prüft ausgewählte Routen.
Serverstand: 2026-10-09T19:06:11.309031Z.

| Radius | Gesamt | Ringe | Powerplay | Märkte | Abdeckung Ringe |
|---|---:|---:|---:|---:|---|
| 250 LY | 13.00 s | 24,459 | 31,744 | 1,133 | vollständig |
| 500 LY | 17.05 s | 48,054 | 35,370 | 1,127 | bestehende Server-Obergrenze erreicht |

Beide Abrufe erfolgreich, ED-Frame und Ardent liefern Märkte, EDData ist nicht
nötig. Die Ring-Domäne bestimmt die Laufzeit; Domänen laufen parallel. 500 LY
bestätigt ausdrücklich keine vollständige externe Ring-Abdeckung.
Diese variablen Live-Eingaben sind nicht Teil des Ergebnisgleichheitsvergleichs.

## 2. Gezielte Änderungen

- Commodity-/Methoden-/Ringregeln, Ring-Kompatibilität und Namen einmal je
  Anfrage vorbereiten. Keine dauerhafte Ergebniscache-Erweiterung.
- Eine exakte Markt-Abfrage innerhalb des kurzlebigen Planungsworkers für
  Routen und Diagnose verwenden. Andere Abfragen, Folge-Suchen, Profile und
  Verifikationspässe lesen erneut; Aufräumen auch bei Fehlern.
- Den verwendeten Ring-Snapshot in den Hintergrundplaner übernehmen, damit ein
  freier Startname seine bekannten Koordinaten behält. Ein anderer Warm-Target
  kann dadurch keine regionalen Märkte mehr aus dieser Suche ausschließen.
- Die zuvor lokal vorbereitete, begrenzte Spansh-Powerplay-Erweiterung bleibt
  enthalten; der Community-Schalter und die ursprünglichen Quellzeiten gelten.

## 3. Ergebnis- und Reihenfolgevergleich

Ausgangsmodul vor diesen Performance-/Koordinatenänderungen separat gesichert.
Beide CPU-Seiten verwenden dieselben öffentlichen Eingaben und bekannten
Origin-Koordinaten. **Alle Felder und Reihenfolge der jeweils 100 Ergebnisse
sind in allen vier Fällen identisch**, auch über drei Wiederholungen; vollständige
JSON-Vergleiche plus SHA-256. Die fertigen vier QML-Selektionen bestätigen
zusätzlich genau dieselben 100 Routenschlüssel in derselben Reihenfolge.

Die zusätzliche Origin-Fehlerkorrektur ändert bewusst die vorher fehlerhafte
QML-Auswahl, indem ausgelassene regionale Märkte wieder berücksichtigt werden.
Sie wird nicht als reine Performance-Äquivalenz dargestellt. Fünf neue
Regressionstests prüfen Evidenzpriorität, unbekannte Ringe/Methodenwechsel,
begrenzte Regelberechnung, unabhängige Ergebnis-Dicts, genau abgegrenzte
Marktreuse und den abgefangenen Origin-Snapshot nach Austausch live gehaltener
Daten. Frische, Filter und Rangfolge bleiben an Fakten gebunden.

## 4. Release-Vorbereitung und Prüfung

- **1.309 App-Tests** inklusive dynamischer QML-Prüfungen: PASS, 123,8 s.
- **158 Servertests** einschließlich nativer ASGI-Route: PASS.
- **24 echte PostgreSQL-Prüfassertionen**: PASS. Lokale Projektions-, Lookup-,
  Upsert- und Handlerquellen laufen nur in einem kurzlebigen Server-Testprozess.
  Ein eigens erzeugtes Schema enthält ausschließlich synthetische Daten;
  HTTP läuft außerhalb DB-Transaktionen, Originalzeiten bleiben erhalten,
  neuere/gleich datierte EDDN-Rennen gewinnen. Das Schema wurde entfernt und
  sein Fehlen bestätigt. Produktivtabellen, installierte Quellen und Dienste
  wurden nicht geändert.
- Sauberer Windows-Build mit PyInstaller 6.22.3; EXE-Ressourcen **1.0.7**.
  Fremde ICU-Runtimes werden ausgeschlossen. Die gebaute EXE besteht den
  echten asynchronen Smoke-Test für **33 Bereiche**, Exit 0.
- README, Changelog, beide 1.0-Anleitungen, Portable-Hinweise und Server-Doku
  beschreiben den Kandidaten und die notwendige Serverkopplung.
- Repository-Hygiene, neue Dateiinhalte und `git diff --check`: PASS.

EXE SHA-256: `147c2068354d01256baed1e46daf13ebc3509f1c3834a468dcf249c2c69c94ec`.

Windows- und Full-Project-ZIP werden aus genau diesem lokalen Arbeitsstand
gepackt, einschließlich neuer uncommitteter Quelldateien. Private Profile,
Journale, Zugangsdaten, Testdatenbanken und Testverzeichnisse sind ausgeschlossen.
Archiv-CRC und Privacy-Dateiliste werden geprüft. `candidate-manifest.json`
enthält jeden gepackten Quellhash, Git-Ausgangscommit und Archividentitäten;
`SHA256SUMS.txt` enthält die beiden ZIP-Prüfsummen. Die geprüfte EXE wird nicht
in die bestehende Installation kopiert.

Die Veröffentlichung bleibt ein gemeinsamer Folgeschritt. Vorher sind die
verbleibenden ALL-COMMODITIES-Latenz-/RAM-Grenzen zu berücksichtigen und der
passende Server 0.9.2 mit den üblichen Backup-/Health-Schritten auszurollen.
Die vorbereiteten Artefakte sind ausdrücklich lokale, unveröffentlichte Kandidaten.

## Reproduktion und lokale Messartefakte

Werkzeuge: `tools/benchmark_mining_complete.py` für konsistente öffentliche
Kopien und Domain-Worker; `tools/benchmark_mining_baseline.py --fixture` für
isolierte Qt/QML-Workflows. Kein realer Profil-Controller wird dafür gestartet.
Interne Rohmessungen bleiben unter `.test-tmp/mining-complete-20261009`:
`cpu-comparison.json`, `qml-comparison.json`, `live-refresh.json`,
`postgres-proof.json`, getrennte Routen/Profilergebnisse und native Logs.
Dieser Bericht enthält nur aggregierte Ergebnisse.
